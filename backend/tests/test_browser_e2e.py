import os
import shutil
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
        node_command = shutil.which("node")
        if not node_command:
            raise RuntimeError("Node.js executable is required to run browser E2E")
        vite_entry = FRONTEND / "node_modules" / "vite" / "bin" / "vite.js"
        if not vite_entry.exists():
            raise RuntimeError("Frontend dependencies are not installed; run npm ci in frontend")
        frontend = subprocess.Popen(
            [node_command, str(vite_entry), "--host", "127.0.0.1", "--port", str(web_port), "--strictPort"],
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
    browser.wait_for_function("""() => {
      const button = Array.from(document.querySelectorAll("button")).find(el => el.textContent.trim().includes("SAVE & CONTINUE"));
      return Boolean(button && !button.disabled);
    }""", timeout=15000)

    browser.get_by_label("First name").fill("Browser")
    browser.get_by_label("Last name").fill("Customer")
    browser.get_by_label("Street address").fill("10 E2E Test Street")
    browser.get_by_label("City").select_option("Coimbatore")
    browser.get_by_label("Area / locality").select_option("Vadavalli")
    profile_requests = []
    profile_responses = []
    browser_errors = []
    browser.on("request", lambda request: profile_requests.append(request) if "/api/v2/customer/profile" in request.url and request.method == "PATCH" else None)
    browser.on("response", lambda response: profile_responses.append(response) if "/api/v2/customer/profile" in response.url and response.request.method == "PATCH" else None)
    browser.on("pageerror", lambda error: browser_errors.append(str(error)))
    save_button = browser.get_by_role("button", name="SAVE & CONTINUE")
    assert save_button.is_enabled(), "Profile save button is unexpectedly disabled"
    with browser.expect_response(lambda r: "/api/v2/customer/profile" in r.url and r.request.method == "PATCH", timeout=15000) as response_info:
        save_button.click()
    response = response_info.value
    assert profile_requests, f"Save click did not issue profile PATCH. URL={browser.url}; page errors={browser_errors}; button enabled={save_button.is_enabled()}"
    assert profile_responses, f"Profile PATCH request had no response. Requests={[request.url for request in profile_requests]}; page errors={browser_errors}"
    assert response.status == 200, f"Profile PATCH returned {response.status}. URL={response.url}; page errors={browser_errors}"
    response_body = response.json()
    assert response_body["profile_complete"] is True, f"Profile PATCH did not report completion: {response_body}"
    assert response_body["first_name"] == "Browser"
    assert response_body["last_name"] == "Customer"
    assert response_body["street_address"] == "10 E2E Test Street"
    assert response_body["city"] == "Coimbatore"
    assert response_body["locality"] == "Vadavalli"
    saved_profile = browser.evaluate("""async (apiUrl) => {
      const account = JSON.parse(localStorage.getItem("lushora-customer"));
      const response = await fetch(apiUrl + "/api/v2/customer/profile", {
        headers: { Authorization: "Bearer " + account.access_token }
      });
      return {status: response.status, body: await response.json()};
    }""", e2e_servers["api"])
    assert saved_profile["status"] == 200
    assert saved_profile["body"]["first_name"] == "Browser"
    assert saved_profile["body"]["last_name"] == "Customer"
    assert saved_profile["body"]["street_address"] == "10 E2E Test Street"
    assert saved_profile["body"]["city"] == "Coimbatore"
    assert saved_profile["body"]["locality"] == "Vadavalli"
    assert saved_profile["body"]["profile_complete"] is True
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
    browser.get_by_role("heading", name="Dashboard").wait_for(timeout=15000)

    # Admin reviews the submitted business, downloads a private document,
    # approves the application, and verifies it appears in the approved list.
    browser.locator(".adm-nav").filter(has_text="Business Requests").click()
    request_row = browser.get_by_role("row").filter(has_text="Browser Test Salon")
    request_row.wait_for(timeout=15000)
    request_row.get_by_role("button", name="View", exact=True).click()
    browser.get_by_role("heading", name="Browser Test Salon").wait_for(timeout=10000)

    with browser.expect_download(timeout=15000) as download_info:
        browser.locator(".adm-docs button").filter(has_text="Aadhaar").click()
    downloaded = download_info.value
    assert downloaded.suggested_filename.endswith("_aadhaar_verification.pdf")

    browser.get_by_placeholder("Review notes or rejection reason").fill("E2E documents reviewed")
    browser.get_by_role("button", name="Approve", exact=True).click()
    browser.locator(".adm-nav").filter(has_text="Approved Businesses").click()
    approved_row = browser.get_by_role("row").filter(has_text="Browser Test Salon")
    approved_row.wait_for(timeout=15000)
    assert "approved" in approved_row.inner_text().lower()

    # The provider account created earlier must now be able to enter the
    # business dashboard and use owner-scoped profile, staff, branch and
    # availability workflows after Admin approval.
    browser.goto(e2e_servers["web"] + "/business")
    browser.get_by_role("heading", name="Dashboard").wait_for(timeout=15000)
    browser.get_by_text("Browser Test Salon", exact=False).first.wait_for(timeout=10000)

    browser.locator(".biz-sidebar button").filter(has_text="Business Profile").click()
    browser.get_by_label("Business description").fill("Verified business profile updated by browser E2E.")
    browser.get_by_role("button", name="Save business profile", exact=True).click()
    browser.get_by_text("Business profile updated successfully.", exact=True).wait_for(timeout=10000)

    browser.locator(".biz-sidebar button").filter(has_text="Staff").click()
    browser.get_by_label("Full name").fill("E2E Senior Stylist")
    browser.get_by_label("Role").select_option("manager")
    browser.get_by_label("Phone").fill("9876543011")
    browser.get_by_role("button", name="Add team member", exact=True).click()
    browser.get_by_text("Team member added.", exact=True).wait_for(timeout=10000)
    browser.get_by_text("E2E Senior Stylist", exact=True).wait_for(timeout=10000)

    browser.locator(".biz-sidebar button").filter(has_text="Locations").click()
    browser.get_by_label("Branch name").fill("E2E Chennai Branch")
    browser.get_by_label("City").select_option("Chennai")
    browser.get_by_label("Locality").fill("Adyar")
    browser.get_by_label("Address").fill("E2E Test Road, Adyar, Chennai")
    browser.get_by_label("Branch phone").fill("9876543012")
    browser.get_by_role("button", name="Add location", exact=True).click()
    browser.get_by_text("Branch added.", exact=True).wait_for(timeout=10000)
    browser.get_by_text("E2E Chennai Branch", exact=True).wait_for(timeout=10000)

    browser.locator(".biz-sidebar button").filter(has_text="Services").click()
    browser.get_by_label("New service name").fill("Signature Haircut")
    browser.get_by_label("New service price (INR)").fill("1500")
    browser.get_by_label("New service duration (minutes)").fill("60")
    browser.get_by_role("button", name="Add service", exact=True).click()
    browser.get_by_role("status").filter(has_text="Service added.").wait_for(timeout=10000)
    service_card = browser.locator(".biz-servicecards article").filter(has_text="Signature Haircut")
    service_card.wait_for(timeout=10000)
    service_card.get_by_role("button", name="Edit", exact=True).click()
    browser.get_by_label("Edit service name").fill("Premium Hair Styling")
    browser.get_by_label("Edit service price (INR)").fill("1800")
    browser.get_by_label("Edit service duration (minutes)").fill("75")
    service_card.get_by_role("button", name="Save service", exact=True).click()
    browser.get_by_role("status").filter(has_text="Service updated.").wait_for(timeout=10000)
    updated_service_card = browser.locator(".biz-servicecards article").filter(has_text="Premium Hair Styling")
    updated_service_card.wait_for(timeout=10000)
    assert "₹1,800" in updated_service_card.inner_text()
    with browser.expect_event("dialog") as confirmation:
        updated_service_card.get_by_role("button", name="Delete", exact=True).click()
    confirmation.value.accept()
    browser.get_by_role("status").filter(has_text="Service deleted.").wait_for(timeout=10000)
    assert browser.locator(".biz-servicecards article").filter(has_text="Premium Hair Styling").count() == 0
    browser.locator(".biz-sidebar button").filter(has_text="Availability").click()
    browser.get_by_label("Opening time").fill("10:00")
    browser.get_by_label("Closing time").fill("19:00")
    browser.get_by_role("button", name="Save availability", exact=True).click()
    browser.get_by_text("Availability settings saved.", exact=True).wait_for(timeout=10000)



def test_admin_recovery_link_opens_reset_request_page(browser, e2e_servers):
    browser.goto(e2e_servers["web"] + "/admin/login")
    browser.get_by_role("link", name="Forgot your password?").click()
    browser.wait_for_url("**/admin/recovery")
    browser.get_by_role("heading", name="Reset your Admin password").wait_for()
    browser.get_by_label("Admin email").fill("e2e-admin@lushora.test")
    browser.get_by_role("button", name="SEND RECOVERY EMAIL").click()
    browser.get_by_role("status").wait_for()
    assert "If the details match" in browser.get_by_role("status").inner_text()


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
