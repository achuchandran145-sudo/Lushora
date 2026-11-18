import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";

const API = "http://127.0.0.1:8000/api";
const categories = [
  { name: "All", icon: "✦", note: "Everything in one place" },
  { name: "Makeup", icon: "✧", note: "Artists & bridal looks" },
  { name: "Salon", icon: "⌁", note: "Hair, skin & grooming" },
  { name: "Skin Clinic", icon: "✺", note: "Expert-led skincare" },
  { name: "Nail Studio", icon: "◇", note: "Nail care & art" },
];
const money = n => `₹${Number(n || 0).toLocaleString("en-IN")}`;

function App() {
  const [providers, setProviders] = useState([]);
  const [bookings, setBookings] = useState([]);
  const [summary, setSummary] = useState({});
  const [category, setCategory] = useState("All");
  const [city, setCity] = useState("All");
  const [search, setSearch] = useState("");
  const [verifiedOnly, setVerifiedOnly] = useState(false);
  const [sort, setSort] = useState("recommended");
  const [page, setPage] = useState("discover");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState(null);
  const [profile, setProfile] = useState(null);
  const [form, setForm] = useState({ name: "", phone: "", date: "", notes: "" });

  async function request(path, options) {
    const response = await fetch(`${API}${path}`, options);
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Something went wrong");
    return data;
  }
  async function refresh() {
    try {
      const [p, b, s] = await Promise.all([
        request("/providers"), request("/bookings"), request("/admin/summary")
      ]);
      setProviders(p); setBookings(b); setSummary(s);
    } catch {
      setNotice("Cannot connect to the LUSHORA API. Start the application using RUN_LUSHORA.bat.");
    }
  }
  useEffect(() => { refresh(); }, []);

  async function seed() {
    setLoading(true);
    try {
      const result = await request("/admin/demo-seed", { method: "POST" });
      setNotice(result.message);
      await refresh();
    } catch (e) { setNotice(e.message); }
    finally { setLoading(false); }
  }
  const filtered = useMemo(() => {
    let list = providers.filter(p =>
      (category === "All" || p.category === category) &&
      (city === "All" || p.city === city) &&
      (!verifiedOnly || p.verified) &&
      (`${p.name} ${p.locality} ${p.city} ${p.description} ${p.category}`.toLowerCase().includes(search.toLowerCase()))
    );
    if (sort === "rating") list = [...list].sort((a,b) => b.rating-a.rating);
    if (sort === "name") list = [...list].sort((a,b) => a.name.localeCompare(b.name));
    return list;
  }, [providers, category, city, verifiedOnly, search, sort]);

  async function submitBooking(e) {
    e.preventDefault();
    if (!selected) return;
    try {
      const result = await request("/bookings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          customer_name: form.name, customer_phone: form.phone,
          provider_id: selected.provider.id, service_id: selected.service.id,
          appointment_at: new Date(form.date).toISOString(), notes: form.notes
        })
      });
      setNotice(`Your request has been created. Reference #${result.id}. The provider has not confirmed it yet.`);
      setSelected(null); setForm({name:"",phone:"",date:"",notes:""});
      await refresh(); setPage("bookings");
    } catch (e) { setNotice(e.message); }
  }

  const iconFor = cat => ({ Makeup:"✧", Salon:"⌁", "Skin Clinic":"✺", "Nail Studio":"◇" }[cat] || "✦");
  const artFor = cat => `art-${cat.toLowerCase().replaceAll(" ","-")}`;

  return <div className="app-shell">
    <header className="topbar">
      <a className="brand" href="#" onClick={() => setPage("discover")}><span className="brand-mark">✿</span><span>LUSHORA</span><small>BEAUTY · WELLNESS · SKIN CARE</small></a>
      <nav className="nav-links">
        {[["discover","Discover"],["bookings","My bookings"],["business","For business"]].map(([id,label]) =>
          <button key={id} className={page===id?"nav-active":""} onClick={()=>setPage(id)}>{label}</button>)}
      </nav>
      <button className="header-cta" onClick={()=>setPage("business")}>List your business <span>↗</span></button>
    </header>

    <main>
      {page === "discover" && <>
        <section className="hero">
          <div className="hero-copy">
            <div className="eyebrow light">YOUR BEAUTY, YOUR WAY</div>
            <h1>Make time for<br/><em>feeling beautiful.</em></h1>
            <p>Discover trusted beauty and wellness professionals around you. Compare services, explore their work and request your next appointment.</p>
            <button className="hero-button" onClick={()=>document.getElementById("explore")?.scrollIntoView({behavior:"smooth"})}>Explore services <span>↓</span></button>
          </div>
          <div className="hero-art">
            <div className="hero-orbit orbit-one"></div><div className="hero-orbit orbit-two"></div>
            <div className="hero-sun"></div><div className="hero-caption"><span>THE LUSHORA EDIT</span><b>Discover your<br/>next ritual.</b><small>Beauty begins with you.</small></div>
            <div className="hero-stamp">CURATED<br/>WITH CARE</div>
          </div>
          <div className="hero-foot"><span>01 — DISCOVER</span><span>BEAUTY & WELLNESS, REIMAGINED</span><span>SCROLL TO EXPLORE ↓</span></div>
        </section>

        <section className="intro-row" id="explore">
          <div><div className="eyebrow">A LITTLE MORE YOU</div><h2>Find your kind<br/>of <em>beautiful.</em></h2></div>
          <p>From the perfect haircut to a little self-care, find local experts who make you feel your best. Thoughtfully brought together in one place.</p>
        </section>

        <section className="category-grid">
          {categories.slice(1).map((c,i)=><button className={`category-tile tile-${i}`} key={c.name} onClick={()=>{setCategory(c.name);document.getElementById("provider-list")?.scrollIntoView({behavior:"smooth"});}}>
            <span className="tile-icon">{c.icon}</span><span className="tile-title">{c.name}</span><span className="tile-note">{c.note}</span><span className="tile-arrow">↗</span>
          </button>)}
        </section>

        <section className="provider-section" id="provider-list">
          <div className="section-heading"><div><div className="eyebrow">THE LOCAL DIRECTORY</div><h2>Meet the <em>experts.</em></h2><p>Find your next favourite beauty destination.</p></div><span className="result-count">{filtered.length.toString().padStart(2,"0")} LISTINGS</span></div>
          <div className="filter-panel">
            <div className="search-wrap"><span>⌕</span><input aria-label="Search providers" placeholder="Search a service, provider or locality..." value={search} onChange={e=>setSearch(e.target.value)}/></div>
            <select aria-label="Choose city" value={city} onChange={e=>setCity(e.target.value)}><option>All</option>{["Coimbatore","Chennai","Tiruvannamalai"].map(x=><option key={x}>{x}</option>)}</select>
            <select aria-label="Sort providers" value={sort} onChange={e=>setSort(e.target.value)}><option value="recommended">Recommended</option><option value="rating">Top rated</option><option value="name">Name A–Z</option></select>
            <label className="verified-filter"><input type="checkbox" checked={verifiedOnly} onChange={e=>setVerifiedOnly(e.target.checked)}/> Verified only</label>
            <button className="seed-button" onClick={seed} disabled={loading}>{loading?"Loading…":"Load demo listings"}</button>
          </div>
          <div className="category-pills">{categories.map(c=><button key={c.name} onClick={()=>setCategory(c.name)} className={category===c.name?"selected-pill":""}>{c.icon} {c.name}</button>)}</div>
          {notice && <button className="notice" onClick={()=>setNotice("")}>{notice}<span>×</span></button>}
          {filtered.length ? <div className="provider-grid">{filtered.map((p,i)=><article className="provider-card" key={p.id}>
            <button className={`provider-art ${artFor(p.category)}`} onClick={()=>setProfile(p)} aria-label={`View ${p.name}`}><span className="art-number">L / {String(i+1).padStart(2,"0")}</span><span className="art-symbol">{iconFor(p.category)}</span><span className="art-category">{p.category}</span><span className="art-open">VIEW PROFILE ↗</span></button>
            <div className="provider-info"><div className="provider-meta"><span>{p.locality}, {p.city}</span><span className="rating">★ {Number(p.rating).toFixed(1)}</span></div><h3>{p.name}</h3><p>{p.description}</p><div className="provider-tags">{p.verified&&<span>✓ Verified</span>}<span>{p.services.length} services</span></div>
              <div className="service-preview">{p.services.slice(0,2).map(s=><button key={s.id} onClick={()=>setSelected({provider:p,service:s})}><span>{s.name}<small>{s.duration_minutes} min</small></span><b>{money(s.price_inr)}</b></button>)}</div>
              <button className="profile-link" onClick={()=>setProfile(p)}>Explore provider <span>→</span></button>
            </div>
          </article>)}</div> : <div className="empty-state"><div className="empty-symbol">✧</div><h3>Your next favourite is waiting.</h3><p>No listings match these filters yet. Try another category or load sample listings to explore the experience.</p><button className="dark-button" onClick={()=>{setCategory("All");setCity("All");setSearch("");setVerifiedOnly(false);seed();}}>Explore sample listings</button></div>}
        </section>

        <section className="business-banner"><div><div className="eyebrow light">FOR BEAUTY PROFESSIONALS</div><h2>Your craft deserves<br/><em>to be discovered.</em></h2><p>Bring your services to a community looking for their next beauty and wellness experience.</p><button className="light-button" onClick={()=>setPage("business")}>Grow with LUSHORA ↗</button></div><div className="banner-decoration"><span>✿</span><small>YOUR BUSINESS.<br/>MORE BEAUTIFULLY<br/>CONNECTED.</small></div></section>
      </>}

      {page === "bookings" && <section className="inner-page"><div className="eyebrow">YOUR LUSHORA JOURNEY</div><h1>My <em>bookings.</em></h1><p className="lead">Keep track of the appointments you've requested.</p><div className="booking-stats"><div><b>{bookings.length}</b><span>Total requests</span></div><div><b>{bookings.filter(b=>b.status==="requested").length}</b><span>Awaiting response</span></div></div>
        {bookings.length ? <div className="booking-list">{bookings.map(b=><article key={b.id} className="booking-row"><div className="booking-date"><b>{new Date(b.appointment_at).toLocaleDateString("en-IN",{day:"2-digit"})}</b><span>{new Date(b.appointment_at).toLocaleDateString("en-IN",{month:"short",year:"numeric"})}</span></div><div><b>Booking request #{b.id}</b><p>{new Date(b.appointment_at).toLocaleTimeString("en-IN",{hour:"2-digit",minute:"2-digit"})} · Customer: {b.customer_name}</p></div><span className="status">{b.status}</span></article>)}</div> : <div className="empty-state"><div className="empty-symbol">⌁</div><h3>No bookings yet</h3><p>Your appointment requests will appear here after you choose a service.</p><button className="dark-button" onClick={()=>setPage("discover")}>Discover services</button></div>}
      </section>}

      {page === "business" && <section className="inner-page business-page"><div className="eyebrow">FOR SALONS, ARTISTS & CLINICS</div><h1>Let your business<br/><em>shine brighter.</em></h1><p className="lead">A place to showcase your services and connect with people looking for beauty and wellness experiences.</p><div className="business-metrics"><div><b>{summary.providers||0}</b><span>Demo providers</span></div><div><b>{summary.services||0}</b><span>Listed services</span></div><div><b>{summary.bookings||0}</b><span>Booking requests</span></div></div><div className="business-columns"><article><span>01</span><h3>Showcase your work</h3><p>Present your services, pricing and business details in one discoverable profile.</p></article><article><span>02</span><h3>Receive requests</h3><p>Give customers a simple way to request an appointment with your business.</p></article><article><span>03</span><h3>Grow your reach</h3><p>Help more local customers discover your beauty and wellness services.</p></article></div><div className="notice business-notice">Provider self-registration, secure provider accounts and live business management are not implemented in this prototype yet.</div><button className="dark-button" onClick={()=>setPage("discover")}>Back to discovery</button></section>}
    </main>

    <footer><div className="footer-brand">✿ LUSHORA</div><p>Beauty, wellness & a little more you.</p><span>© 2026 LUSHORA · CONCEPT MARKETPLACE</span></footer>

    {profile && <div className="modal-backdrop" onMouseDown={e=>e.target===e.currentTarget&&setProfile(null)}><section className="profile-modal"><button className="modal-close" onClick={()=>setProfile(null)}>×</button><div className={`profile-cover ${artFor(profile.category)}`}><span>{iconFor(profile.category)}</span></div><div className="profile-content"><div className="eyebrow">{profile.category} · {profile.locality}, {profile.city}</div><h2>{profile.name}</h2><p>{profile.description}</p><div className="provider-tags">{profile.verified&&<span>✓ Verified listing</span>}<span>★ {profile.rating} rating</span></div><h3>Services & pricing</h3>{profile.services.map(s=><button className="profile-service" key={s.id} onClick={()=>{setSelected({provider:profile,service:s});setProfile(null);}}><span>{s.name}<small>{s.duration_minutes} minutes</small></span><b>{money(s.price_inr)}　→</b></button>)}</div></section></div>}

    {selected && <div className="modal-backdrop" onMouseDown={e=>e.target===e.currentTarget&&setSelected(null)}><form className="booking-modal" onSubmit={submitBooking}><button type="button" className="modal-close" onClick={()=>setSelected(null)}>×</button><div className="eyebrow">APPOINTMENT REQUEST</div><h2>Make it a <em>date.</em></h2><p className="booking-for">{selected.provider.name} · {selected.service.name}</p><div className="booking-price">{money(selected.service.price_inr)} <small>· {selected.service.duration_minutes} min</small></div>
      <label>Your name<input required minLength="2" value={form.name} onChange={e=>setForm({...form,name:e.target.value})} placeholder="Full name"/></label>
      <label>Phone number<input required pattern="[0-9+ ()-]{10,20}" value={form.phone} onChange={e=>setForm({...form,phone:e.target.value})} placeholder="Mobile number"/></label>
      <label>Preferred date & time<input required type="datetime-local" min={new Date(Date.now()+60000).toISOString().slice(0,16)} value={form.date} onChange={e=>setForm({...form,date:e.target.value})}/></label>
      <label>Anything we should know? <textarea rows="2" value={form.notes} onChange={e=>setForm({...form,notes:e.target.value})} placeholder="Optional note"/></label>
      <button className="dark-button" type="submit">Send appointment request ↗</button><small className="disclaimer">This creates a request, not a confirmed appointment. Payment and live availability are not enabled in this prototype.</small>
    </form></div>}
  </div>;
}
createRoot(document.getElementById("root")).render(<App />);
