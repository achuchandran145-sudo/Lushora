import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

import pytest
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_http(url, process, log_path, timeout=45):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if process.poll() is not None:
            log_text=Path(log_path).read_text(errors="replace") if Path(log_path).exists() else ""
            raise RuntimeError(f"Server exited early with code {process.returncode}. Log: {log_text[-4000:]}")
        try:
            with urlopen(url, timeout=2) as response:
                if response.status < 500:
                    return
        except Exception:
            time.sleep(0.4)
    log_text=Path(log_path).read_text(errors="replace") if Path(log_path).exists() else ""
    raise RuntimeError(f"Server did not become ready: {url}. Log: {log_text[-4000:]}")


@pytest.fixture(scope="session")
def e2e_servers(tmp_path_factory):
    data_dir = tmp_path_factory.mktemp("lushora-browser-e2e")
    api_port, web_port = _free_port(), _free_port()
    api_url = f"http://127.0.0.1:{api_port}"
    web_url = f"http://127.0.0.1:{web_port}"
    env = os.environ.copy()
    env.update({
        "APP_ENV": "development",
        "ENVIRONMENT": "development",
        "LUSHORA_DATABASE_URL": f"sqlite:///{(data_dir / 'e2e.db').as_posix()}",
        "LUSHORA_AUTH_SECRET": "browser-e2e-test-secret-which-is-long-enough-123",
        "LUSHORA_OTP_DEV_MODE": "true",
        "LUSHORA_ADMIN_EMAIL": "e2e-admin@lushora.test",
        "LUSHORA_ADMIN_PASSWORD": "StrongAdmin123!",
        "LUSHORA_ADMIN_NAME": "Browser E2E Admin",
        "LUSHORA_CORS_ORIGINS": web_url,
        "PYTHONPATH": str(BACKEND),
        "VITE_LUSHORA_API": api_url + "/api",
    })
    backend_log=data_dir/"backend.log"
    frontend_log=data_dir/"frontend.log"
    with backend_log.open("w") as backend_stream, frontend_log.open("w") as frontend_stream:
        backend = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(api_port)],
            cwd=BACKEND, env=env, stdout=backend_stream, stderr=subprocess.STDOUT,
        )
        frontend = subprocess.Popen(
            ["npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", str(web_port), "--strictPort"],
            cwd=FRONTEND, env=env, stdout=frontend_stream, stderr=subprocess.STDOUT,
        )
        try:
            _wait_http(api_url + "/api/health", backend, backend_log)
            _wait_http(web_url, frontend, frontend_log)
            yield {"api": api_url, "web": web_url}
        finally:
            frontend.terminate()
            backend.terminate()
            try:
                frontend.wait(timeout=10)
            except subprocess.TimeoutExpired:
                frontend.kill()
            try:
                backend.wait(timeout=10)
            except subprocess.TimeoutExpired:
                backend.kill()


@pytest.fixture
def browser():
    with sync_playwright() as p:
        chromium = p.chromium.launch(headless=True)
        context = chromium.new_context(viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        yield page
        context.close()
        chromium.close()


def test_customer_otp_profile_and_mobile_homepage(browser, e2e_servers):
    browser.goto(e2e_servers["web"] + "/customer/login")
    phone = browser.get_by_placeholder("+91 98765 43210")
    phone.fill("9876543000")
    browser.get_by_role("button", name="SEND OTP").click()

    otp_input = browser.get_by_placeholder("Enter 6-digit OTP")
    otp_input.wait_for(timeout=10000)
    assert len(otp_input.input_value()) == 6, "Development OTP should be populated by the OTP request response"
    otp_input.fill(otp_input.input_value())
    browser.get_by_role("button", name="VERIFY & CONTINUE").click()
    browser.wait_for_url("**/customer/profile", timeout=15000)

    browser.get_by_label("First name").fill("Browser")
    browser.get_by_label("Last name").fill("Customer")
    browser.get_by_label("Street address").fill("10 E2E Test Street")
    browser.get_by_label("City").select_option("Coimbatore")
    browser.get_by_label("Area / locality").select_option("Vadavalli")
    with browser.expect_response(lambda response: "/api/v2/customer/profile" in response.url and response.request.method == "PATCH", timeout=15000) as profile_response:
        browser.get_by_role("button", name="SAVE & CONTINUE").click()
    response = profile_response.value
    assert response.status == 200, f"Customer profile PATCH failed: {response.status} {response.text()}"
    browser.get_by_text("Profile saved successfully.", exact=True).wait_for(timeout=5000)
    browser.wait_for_function("window.location.pathname === '/'", timeout=10000)
    browser.goto(e2e_servers["web"] + "/")

    browser.set_viewport_size({"width": 390, "height": 844})
    browser.reload()
    browser.wait_for_load_state("domcontentloaded")
    overflow = browser.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1")
    assert not overflow, "Homepage horizontally overflows the mobile viewport"
    assert browser.locator(".wordmark").count() >= 1


def test_guest_discovery_and_booking_request(browser, e2e_servers):
    from datetime import date, timedelta
    import json
    import urllib.request

    seed_request=urllib.request.Request(e2e_servers["api"]+"/api/admin/demo-seed",data=b"{}",headers={"Content-Type":"application/json"},method="POST")
    with urllib.request.urlopen(seed_request,timeout=10) as response:
        assert response.status==200

    browser.goto(e2e_servers["web"]+"/")
    browser.locator(".category-chip").filter(has_text="Salon").click(timeout=15000)
    assert browser.get_by_text("Glow & Glam Salon",exact=True).count()==1
    browser.get_by_role("button",name="Book",exact=True).first.click()

    target=date.today()+timedelta(days=2)
    while target.weekday()==6:
        target+=timedelta(days=1)
    date_input=browser.get_by_label("Appointment date")
    date_input.fill(target.isoformat())
    browser.get_by_text("Available time slots").wait_for(timeout=15000)
    slot_buttons=browser.locator(".available-slot-list button")
    assert slot_buttons.count()>0, "Demo provider should have available slots on the selected working day"
    slot_buttons.first.click()
    browser.get_by_label("Your name").fill("E2E Guest")
    browser.get_by_label("Mobile number").fill("9876543002")
    browser.get_by_role("button",name="Send booking request").click()
    browser.get_by_text("Your booking request has been received",exact=False).wait_for(timeout=15000)

def test_business_signup_and_admin_login(browser, e2e_servers):
    browser.goto(e2e_servers["web"] + "/business/login")
    browser.get_by_role("button", name="Create a business account").click()
    browser.get_by_label("Owner name").fill("Browser Provider")
    browser.get_by_label("Business / admin email").fill("browser-provider@lushora.test")
    browser.get_by_label("Mobile number").fill("9876543001")
    browser.get_by_label("Password").fill("StrongProvider123!")
    browser.get_by_role("button", name="CREATE BUSINESS ACCOUNT").click()
    browser.wait_for_url("**/business/onboarding", timeout=15000)
    assert browser.get_by_role("heading", name="Verify your business").count() == 1

    # Exercise the provider verification submission and private-document upload journey.
    browser.get_by_label("Business name").fill("Browser Test Salon")
    browser.get_by_label("Salon").check()
    browser.get_by_label("City").fill("Coimbatore")
    browser.get_by_label("Locality / Area").fill("Vadavalli")
    browser.get_by_label("Full business address").fill("E2E Test Address, Vadavalli, Coimbatore")
    browser.get_by_label("Aadhaar last 4 digits only").fill("1234")
    browser.get_by_label("PAN number").fill("ABCDE1234F")
    test_pdf = {"name": "test-document.pdf", "mimeType": "application/pdf", "buffer": b"%PDF-1.4\\nLUSHORA E2E TEST DOCUMENT\\n%%EOF"}
    for label in ["Aadhaar document", "PAN document", "Business proof (GST / registration / license)"]:
        browser.get_by_label(label).set_input_files(test_pdf)
    browser.get_by_role("button", name="SUBMIT FOR ADMIN VERIFICATION").click()
    browser.get_by_text("Verification submitted. Your business is pending admin review.", exact=True).wait_for(timeout=15000)

    browser.goto(e2e_servers["web"] + "/admin/login")
    browser.get_by_label("Business / admin email").fill("e2e-admin@lushora.test")
    browser.get_by_label("Password").fill("StrongAdmin123!")
    browser.get_by_role("button", name="SIGN IN").click()
    browser.wait_for_url("**/admin", timeout=15000)
    assert browser.get_by_role("heading", name="Dashboard").count() == 1


def test_homepage_and_customer_login_accessibility_audit(browser, e2e_servers):
    axe_script = FRONTEND / "node_modules" / "axe-core" / "axe.min.js"
    assert axe_script.exists(), "CI must install axe-core before browser E2E"
    violations = []
    for route in ("/", "/customer/login", "/business/login", "/admin/login"):
        browser.goto(e2e_servers["web"] + route)
        browser.add_script_tag(path=str(axe_script))
        results = browser.evaluate("""async () => {
            const result = await axe.run(document, {
                runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] }
            });
            return result.violations.map(v => ({
                id: v.id,
                impact: v.impact,
                description: v.description,
                nodes: v.nodes.map(n => ({ target: n.target, summary: n.failureSummary }))
            }));
        }""")
        violations.extend({"route": route, **v} for v in results)
    serious = [v for v in violations if v["impact"] in ("serious", "critical")]
    assert not serious, "Serious/critical accessibility violations: " + str(serious)


def test_primary_routes_have_no_mobile_horizontal_overflow(browser, e2e_servers):
    for width in (360, 390, 768):
        browser.set_viewport_size({"width": width, "height": 844})
        for route in ("/", "/customer/login", "/business/login", "/admin/login"):
            browser.goto(e2e_servers["web"] + route)
            browser.wait_for_load_state("domcontentloaded")
            overflow = browser.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1")
            assert not overflow, f"Horizontal overflow at {width}px on route {route}"


def test_keyboard_navigation_has_visible_focus_on_customer_login(browser, e2e_servers):
    browser.goto(e2e_servers["web"] + "/customer/login")
    browser.keyboard.press("Tab")
    focus = browser.evaluate("""() => {
      const el = document.activeElement;
      const style = getComputedStyle(el);
      return {tag: el.tagName, outlineWidth: style.outlineWidth, outlineStyle: style.outlineStyle, outlineColor: style.outlineColor};
    }""")
    assert focus["tag"] != "BODY", "Keyboard Tab should move focus to an interactive element"
    assert focus["outlineStyle"] != "none" and focus["outlineWidth"] != "0px", "Keyboard focus must be visibly outlined"
