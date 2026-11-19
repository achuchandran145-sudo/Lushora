import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';

const API = import.meta.env.VITE_LUSHORA_API || 'http://127.0.0.1:8000/api';
const categories = [
  { name: 'All experiences', icon: '✧', key: 'All' },
  { name: 'Makeup', icon: '◈', key: 'Makeup' },
  { name: 'Salon', icon: '✂', key: 'Salon' },
  { name: 'Skin Clinic', icon: '✿', key: 'Skin Clinic' },
  { name: 'Nail Studio', icon: '◇', key: 'Nail Studio' },
];
const cityOptions = ['All cities', 'Chennai', 'Coimbatore', 'Tiruvannamalai'];
const editorial = [
  { title: 'The art of the occasion look', kicker: 'MAKEUP NOTES', image: 'https://images.unsplash.com/photo-1487412947147-5cebf100ffc2?auto=format&fit=crop&w=900&q=85' },
  { title: 'A slower kind of self-care', kicker: 'WELLNESS EDIT', image: 'https://images.unsplash.com/photo-1540555700478-4be289fbecef?auto=format&fit=crop&w=900&q=85' },
  { title: 'Details make the moment', kicker: 'NAIL JOURNAL', image: 'https://images.unsplash.com/photo-1604654894610-df63bc536371?auto=format&fit=crop&w=900&q=85' },
];

function App() {
  const [providers, setProviders] = useState([]);
  const [category, setCategory] = useState('All');
  const [city, setCity] = useState('All cities');
  const [search, setSearch] = useState('');
  const [verifiedOnly, setVerifiedOnly] = useState(false);
  const [notice, setNotice] = useState('');
  const [selected, setSelected] = useState(null);
  const [showAll, setShowAll] = useState(false);
  const [form, setForm] = useState({ name: '', phone: '', date: '' });
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);
  const [authMode, setAuthMode] = useState('login');
  const [authForm, setAuthForm] = useState({ full_name: '', email: '', phone: '', password: '', role: 'customer' });
  const [authOpen, setAuthOpen] = useState(false);
  const [businessOpen, setBusinessOpen] = useState(false);
  const [dashboardOpen, setDashboardOpen] = useState(false);
  const [dashboardData, setDashboardData] = useState(null);
  const [serviceForm, setServiceForm] = useState({ name: '', price_inr: '', duration_minutes: '30' });
  const [businessForm, setBusinessForm] = useState({ name: '', category: 'Salon', city: 'Coimbatore', locality: '', description: '' });
  const [account, setAccount] = useState(() => { try { return JSON.parse(localStorage.getItem('lushora-account') || 'null'); } catch { return null; } });

  async function load() {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (category !== 'All') params.set('category', category);
      if (city !== 'All cities') params.set('city', city);
      if (verifiedOnly) params.set('verified', 'true');
      const [p, s] = await Promise.all([fetch(`${API}/providers?${params}`), fetch(`${API}/admin/summary`)]);
      if (!p.ok) throw new Error('Could not load providers');
      setProviders(await p.json());
      if (s.ok) setSummary(await s.json());
    } catch {
      setNotice('The LUSHORA API is not connected. Start the backend using RUN_LUSHORA.bat.');
    } finally { setLoading(false); }
  }
  useEffect(() => { load(); }, [category, city, verifiedOnly]);

  async function seed() {
    try {
      const r = await fetch(`${API}/admin/demo-seed`, { method: 'POST' });
      const d = await r.json();
      setNotice(d.message || 'Sample listings loaded.');
      await load();
    } catch { setNotice('Could not load sample listings. Check that the backend is running.'); }
  }

  const filtered = useMemo(() => providers.filter(p =>
    `${p.name} ${p.locality} ${p.city} ${p.description}`.toLowerCase().includes(search.toLowerCase())
  ), [providers, search]);
  const visible = showAll ? filtered : filtered.slice(0, 4);

  async function book(e) {
    e.preventDefault();
    if (!selected) return;
    try {
      const r = await fetch(`${API}/bookings`, { method: 'POST', headers: { 'Content-Type': 'application/json', ...(account?.access_token ? { Authorization: 'Bearer ' + account.access_token } : {}) }, body: JSON.stringify({ customer_name: form.name, customer_phone: form.phone, provider_id: selected.provider.id, service_id: selected.service.id, appointment_at: new Date(form.date).toISOString() }) });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || 'Booking request failed');
      setNotice(`Your booking request has been received. Reference #${d.id}.`);
      setSelected(null); setForm({ name: '', phone: '', date: '' }); load();
    } catch (err) { setNotice(err.message); }
  }



  async function openDashboard() {
    setDashboardOpen(true);
    setDashboardData({ loading: true });
    const token = account?.access_token;
    if (!token) return;
    const headers = { Authorization: 'Bearer ' + token };
    try {
      const role = account.user.role;
      if (role === 'customer') {
        const r = await fetch(API + '/customer/me/bookings', { headers });
        if (!r.ok) throw new Error('Unable to load customer bookings');
        setDashboardData({ bookings: await r.json() });
      } else if (role === 'provider') {
        const [p, b] = await Promise.all([fetch(API + '/provider/me', { headers }), fetch(API + '/provider/me/bookings', { headers })]);
        const provider = p.ok ? await p.json() : null;
        const bookings = b.ok ? await b.json() : [];
        setDashboardData({ provider, bookings });
      } else if (role === 'admin') {
        const [s, p, b] = await Promise.all([fetch(API + '/admin/summary', { headers }), fetch(API + '/admin/providers', { headers }), fetch(API + '/admin/bookings', { headers })]);
        setDashboardData({ summary: s.ok ? await s.json() : null, providers: p.ok ? await p.json() : [], bookings: b.ok ? await b.json() : [] });
      }
    } catch (err) { setDashboardData({ error: err.message }); }
  }
  async function updateBookingStatus(id, status) {
    try {
      const r = await fetch(API + '/bookings/' + id + '/status?status=' + status, { method:'PATCH', headers:{ Authorization:'Bearer '+account.access_token } });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || 'Update failed');
      await openDashboard();
    } catch (err) { setNotice(err.message); }
  }
  async function approveProvider(id, status) {
    try {
      const r = await fetch(API + '/admin/providers/' + id + '/approval?status=' + status, { method:'PATCH', headers:{ Authorization:'Bearer '+account.access_token } });
      if (!r.ok) { const d=await r.json(); throw new Error(d.detail || 'Approval failed'); }
      await openDashboard();
    } catch (err) { setNotice(err.message); }
  }


  async function addProviderService(e) {
    e.preventDefault();
    try {
      const params = new URLSearchParams(serviceForm);
      const r = await fetch(API + '/provider/me/services?' + params, { method:'POST', headers:{ Authorization:'Bearer '+account.access_token } });
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail || 'Could not add service');
      setServiceForm({ name:'', price_inr:'', duration_minutes:'30' });
      await openDashboard();
    } catch (err) { setNotice(err.message); }
  }

  async function submitAuth(e) {
    e.preventDefault();
    try {
      const endpoint = authMode === 'register' ? '/auth/register' : '/auth/login';
      const payload = authMode === 'register' ? authForm : { email: authForm.email, password: authForm.password };
      const r = await fetch(API + endpoint, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail || 'Authentication failed');
      setAccount(data); localStorage.setItem('lushora-account', JSON.stringify(data));
      setAuthOpen(false); setNotice('Welcome to LUSHORA. You are signed in.');
    } catch (err) { setNotice(err.message); }
  }

  async function submitBusiness(e) {
    e.preventDefault();
    try {
      const token = account?.access_token;
      if (!token) { setBusinessOpen(false); setAuthMode('register'); setAuthForm({...authForm, role:'provider'}); setAuthOpen(true); setNotice('Create a provider account first, then submit your business.'); return; }
      const r = await fetch(API + '/provider/register', { method:'POST', headers:{ 'Content-Type':'application/json', Authorization:'Bearer '+token }, body:JSON.stringify(businessForm) });
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail || 'Business submission failed');
      setBusinessOpen(false); setNotice(data.message || 'Business submitted for approval.');
    } catch (err) { setNotice(err.message); }
  }

  const scrollToExplore = () => document.getElementById('discover')?.scrollIntoView({ behavior: 'smooth' });
  return <>
    <header className="site-header">
      <a className="wordmark" href="#top" aria-label="LUSHORA home"><span className="mark">✿</span><span>LUSHORA</span><small>BEAUTY · WELLNESS · SKIN</small></a>
      <nav className="main-nav"><a href="#discover">Discover</a><a href="#journal">The Journal</a><a href="#business">For businesses</a></nav>
      <div className="header-actions"><button className="text-button" onClick={() => document.getElementById('business')?.scrollIntoView({ behavior: 'smooth' })}>List your business</button>{account && <button className="text-button" onClick={openDashboard}>Dashboard</button>}<button className="login-button" onClick={() => account ? (localStorage.removeItem('lushora-account'), setAccount(null), setNotice('You have signed out.')) : setAuthOpen(true)}>{account ? 'Sign out' : 'Log in'} <span>↗</span></button></div>
    </header>

    <main id="top">
      <section className="hero">
        <div className="hero-image" />
        <div className="hero-shade" />
        <div className="hero-content">
          <p className="eyebrow light">A MORE BEAUTIFUL WAY TO BOOK</p>
          <h1>Make time for<br/><em>your kind of</em> beautiful.</h1>
          <p className="hero-copy">Discover exceptional salons, makeup artists, skin specialists and nail studios — all in one considered space.</p>
          <button className="hero-cta" onClick={scrollToExplore}>Explore experiences <span>↗</span></button>
        </div>
        <div className="hero-caption"><span>01 / 04</span><i /> CURATED BEAUTY, CLOSE TO HOME</div>
      </section>

      <section className="search-panel" aria-label="Search beauty services">
        <div className="search-intro"><span className="eyebrow">FIND YOUR NEXT APPOINTMENT</span><h2>Where shall we begin?</h2></div>
        <div className="search-controls">
          <label className="search-field"><span>⌕</span><input value={search} onChange={e => setSearch(e.target.value)} placeholder="Service, salon or specialist" /></label>
          <label className="select-field"><span>⌖</span><select value={city} onChange={e => setCity(e.target.value)}>{cityOptions.map(c => <option key={c} value={c}>{c}</option>)}</select></label>
          <button className="search-submit" onClick={scrollToExplore}>Find my experience <span>→</span></button>
        </div>
      </section>

      <section className="category-section" id="discover">
        <div className="section-title"><div><p className="eyebrow">EXPLORE BY EXPERIENCE</p><h2>Consider this your beauty edit.</h2></div><p className="section-note">Thoughtfully selected services<br/>for every version of you.</p></div>
        <div className="category-list">{categories.map(c => <button key={c.key} className={`category-chip ${category === c.key ? 'active' : ''}`} onClick={() => { setCategory(c.key); setShowAll(false); }}><span>{c.icon}</span>{c.name}</button>)}</div>
      </section>

      <section className="provider-section">
        <div className="section-title provider-heading"><div><p className="eyebrow">THE LUSHORA SELECTION</p><h2>Places worth making time for.</h2><p className="subcopy">Discover trusted local experts and their signature services.</p></div><div className="provider-tools"><label className="verified-filter"><input type="checkbox" checked={verifiedOnly} onChange={e => setVerifiedOnly(e.target.checked)} /> Verified only</label><button className="subtle-button" onClick={seed}>Load sample listings</button></div></div>
        {notice && <div className="notice" role="status"><span>{notice}</span><button onClick={() => setNotice('')}>×</button></div>}
        <div className="result-line"><span>{loading ? 'Finding experiences…' : `${filtered.length} ${filtered.length === 1 ? 'place' : 'places'} to explore`}</span><span className="result-location">{city === 'All cities' ? 'Across our launch cities' : city}</span></div>
        {visible.length ? <div className="provider-grid">{visible.map((p, i) => <article className="provider-card" key={p.id}>
          <div className={`provider-image image-${i % 4}`}><span className="provider-category">{p.category}</span><button className="heart" aria-label="Save provider" onClick={() => account ? setNotice('Favourites are not implemented yet.') : setAuthOpen(true)}>♡</button><div className="image-initials">{p.name.split(' ').slice(0, 2).map(x => x[0]).join('')}</div></div>
          <div className="provider-info"><div className="provider-meta"><span>{p.locality}, {p.city}</span>{p.verified && <span className="verified-tag">✦ VERIFIED</span>}</div><h3>{p.name}</h3><div className="rating">★ <b>{Number(p.rating || 0).toFixed(1)}</b><span> · LUSHORA listed specialist</span></div><p className="provider-description">{p.description}</p>
            <div className="service-list">{(p.services || []).slice(0, 2).map(s => <div className="service-row" key={s.id}><div><b>{s.name}</b><small>{s.duration_minutes} min</small></div><div className="service-price">₹{s.price_inr}<button onClick={() => setSelected({ provider: p, service: s })}>Book</button></div></div>)}</div>
          </div>
        </article>)}</div> : <div className="empty-state"><span className="empty-flower">✿</span><h3>Your next favourite place is waiting.</h3><p>{providers.length === 0 ? 'Load sample listings to preview the discovery experience, or connect real providers as they join LUSHORA.' : 'No places match those filters. Try another category, city or search term.'}</p>{providers.length === 0 && <button className="dark-button" onClick={seed}>Explore sample listings <span>→</span></button>}</div>}
        {filtered.length > 4 && <div className="view-all-wrap"><button className="outline-button" onClick={() => setShowAll(!showAll)}>{showAll ? 'Show fewer' : 'View all places'} <span>→</span></button></div>}
      </section>

      <section className="manifesto"><div className="manifesto-image"/><div className="manifesto-copy"><p className="eyebrow light">THE LUSHORA PROMISE</p><h2>Beauty is personal.<br/><em>Your experience should be too.</em></h2><p>Find a place that feels right, choose the service that suits you, and make a little room for yourself.</p><button className="light-button" onClick={scrollToExplore}>Find your moment <span>↗</span></button></div></section>

      <section className="journal-section" id="journal"><div className="section-title"><div><p className="eyebrow">NOTES ON BEAUTY & WELLNESS</p><h2>A little inspiration, thoughtfully chosen.</h2></div><span className="journal-side">THE LUSHORA JOURNAL · 001</span></div><div className="journal-grid">{editorial.map(item => <article className="journal-card" key={item.title}><img src={item.image} alt="Beauty editorial"/><div><span className="eyebrow">{item.kicker}</span><h3>{item.title}</h3><span className="read-link">Explore the story ↗</span></div></article>)}</div></section>

      <section className="business-banner" id="business"><div><p className="eyebrow light">FOR THE PEOPLE BEHIND THE BEAUTY</p><h2>Your craft deserves<br/><em>to be discovered.</em></h2><p>Bring your business to a community looking for their next favourite beauty experience.</p></div><button className="light-button" onClick={() => setBusinessOpen(true)}>List your business <span>↗</span></button></section>
    </main>

    <footer className="site-footer"><div className="footer-top"><a className="wordmark footer-wordmark" href="#top"><span className="mark">✿</span><span>LUSHORA</span></a><p>Discover beauty. Find your people. Make time for you.</p><div className="footer-links"><a href="#discover">Discover</a><a href="#journal">Journal</a><a href="#business">For businesses</a></div></div><div className="footer-bottom"><span>© 2026 LUSHORA. All rights reserved.</span><span>BEAUTY · WELLNESS · SKIN CARE</span></div></footer>

    
    
    {dashboardOpen && <div className="modal-backdrop" onClick={()=>setDashboardOpen(false)}><div className="booking-modal dashboard-modal" onClick={e=>e.stopPropagation()}><button className="modal-close" onClick={()=>setDashboardOpen(false)}>×</button><p className="eyebrow">LUSHORA {account?.user?.role?.toUpperCase()} DASHBOARD</p><h2>{account?.user?.role==='admin'?'Platform overview':account?.user?.role==='provider'?'Business dashboard':'My bookings'}</h2>{dashboardData?.loading && <p>Loading dashboard…</p>}{dashboardData?.error && <p>{dashboardData.error}</p>}{dashboardData?.summary && <div className="dashboard-stats">{Object.entries(dashboardData.summary).map(([k,v])=><div key={k}><strong>{v}</strong><span>{k.replaceAll('_',' ')}</span></div>)}</div>}{dashboardData?.providers && account?.user?.role==='admin' && <><h3>Business approvals</h3>{dashboardData.providers.map(p=><div className="dashboard-row" key={p.id}><div><strong>{p.name}</strong><small>{p.city} · {p.category} · {p.approval_status}</small></div>{p.approval_status==='pending' && <div><button onClick={()=>approveProvider(p.id,'approved')}>Approve</button><button onClick={()=>approveProvider(p.id,'rejected')}>Reject</button></div>}</div>)}</>}{dashboardData?.provider && <div className="dashboard-provider"><h3>{dashboardData.provider.name}</h3><p>Status: {dashboardData.provider.approval_status}</p><p>{dashboardData.provider.services?.length || 0} services listed</p>{dashboardData?.provider?.approval_status==='approved' && <form className="service-add-form" onSubmit={addProviderService}><h3>Manage services</h3><label>Service name<input required value={serviceForm.name} onChange={e=>setServiceForm({...serviceForm,name:e.target.value})}/></label><label>Price (₹)<input type="number" min="0" required value={serviceForm.price_inr} onChange={e=>setServiceForm({...serviceForm,price_inr:e.target.value})}/></label><label>Duration (minutes)<input type="number" min="5" max="600" required value={serviceForm.duration_minutes} onChange={e=>setServiceForm({...serviceForm,duration_minutes:e.target.value})}/></label><button className="dark-button">Add service</button></form>}</div>}{dashboardData?.bookings && <><h3>Bookings</h3>{dashboardData.bookings.length===0 && <p>No bookings yet.</p>}{dashboardData.bookings.map(b=><div className="dashboard-row" key={b.id}><div><strong>Booking #{b.id} · {b.status}</strong><small>{new Date(b.appointment_at).toLocaleString()} · Service #{b.service_id}</small></div>{(account?.user?.role==='provider' || account?.user?.role==='admin') && b.status==='requested' && <div><button onClick={()=>updateBookingStatus(b.id,'confirmed')}>Confirm</button><button onClick={()=>updateBookingStatus(b.id,'rejected')}>Reject</button></div>}{account?.user?.role==='customer' && ['requested','confirmed'].includes(b.status) && <button onClick={()=>updateBookingStatus(b.id,'cancelled')}>Cancel</button>}</div>)}</>}</div></div>}

    {authOpen && <div className="modal-backdrop" onClick={() => setAuthOpen(false)}><form className="booking-modal account-modal" onSubmit={submitAuth} onClick={e=>e.stopPropagation()}><button type="button" className="modal-close" onClick={()=>setAuthOpen(false)}>×</button><p className="eyebrow">LUSHORA ACCOUNT</p><h2>{authMode === 'register' ? 'Create your account' : 'Welcome back'}</h2><div className="auth-switch"><button type="button" onClick={()=>setAuthMode('login')} className={authMode==='login'?'active':''}>Log in</button><button type="button" onClick={()=>setAuthMode('register')} className={authMode==='register'?'active':''}>Register</button></div>{authMode==='register' && <><label>Full name<input required minLength="2" value={authForm.full_name} onChange={e=>setAuthForm({...authForm,full_name:e.target.value})}/></label><label>Mobile number<input value={authForm.phone} onChange={e=>setAuthForm({...authForm,phone:e.target.value})} placeholder="Optional"/></label><label>Account type<select value={authForm.role} onChange={e=>setAuthForm({...authForm,role:e.target.value})}><option value="customer">Customer</option><option value="provider">Beauty business</option></select></label></>}<label>Email<input type="email" required value={authForm.email} onChange={e=>setAuthForm({...authForm,email:e.target.value})}/></label><label>Password<input type="password" required minLength="8" value={authForm.password} onChange={e=>setAuthForm({...authForm,password:e.target.value})}/></label><button className="dark-button full-button">{authMode==='register'?'Create account':'Log in'} <span>→</span></button></form></div>}
    {businessOpen && <div className="modal-backdrop" onClick={()=>setBusinessOpen(false)}><form className="booking-modal" onSubmit={submitBusiness} onClick={e=>e.stopPropagation()}><button type="button" className="modal-close" onClick={()=>setBusinessOpen(false)}>×</button><p className="eyebrow">JOIN THE LUSHORA EDIT</p><h2>List your business</h2><label>Business name<input required value={businessForm.name} onChange={e=>setBusinessForm({...businessForm,name:e.target.value})}/></label><label>Category<select value={businessForm.category} onChange={e=>setBusinessForm({...businessForm,category:e.target.value})}>{['Makeup','Salon','Skin Clinic','Nail Studio'].map(c=><option key={c}>{c}</option>)}</select></label><label>City<select value={businessForm.city} onChange={e=>setBusinessForm({...businessForm,city:e.target.value})}>{cityOptions.slice(1).map(c=><option key={c}>{c}</option>)}</select></label><label>Locality<input value={businessForm.locality} onChange={e=>setBusinessForm({...businessForm,locality:e.target.value})}/></label><label>About your business<textarea value={businessForm.description} onChange={e=>setBusinessForm({...businessForm,description:e.target.value})}/></label><button className="dark-button full-button">Submit for review <span>→</span></button><small className="booking-note">Business listings are reviewed before they appear publicly.</small></form></div>}

    {selected && <div className="modal-backdrop" onClick={() => setSelected(null)}><form className="booking-modal" onSubmit={book} onClick={e => e.stopPropagation()}><button type="button" className="modal-close" onClick={() => setSelected(null)}>×</button><p className="eyebrow">YOUR LUSHORA MOMENT</p><h2>{selected.service.name}</h2><p className="modal-provider">{selected.provider.name} · {selected.provider.locality}, {selected.provider.city}</p><div className="modal-price">₹{selected.service.price_inr}<span> · {selected.service.duration_minutes} minutes</span></div><label>Your name<input required minLength="2" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })}/></label><label>Mobile number<input required minLength="10" value={form.phone} onChange={e => setForm({ ...form, phone: e.target.value })} placeholder="10-digit mobile number"/></label><label>Preferred appointment<input required type="datetime-local" min={new Date(Date.now() + 60000).toISOString().slice(0, 16)} value={form.date} onChange={e => setForm({ ...form, date: e.target.value })}/></label><button className="dark-button full-button">Send booking request <span>→</span></button><small className="booking-note">This preview creates a booking request. Live availability, payment and instant confirmation are not enabled yet.</small></form></div>}
  </>;
}

createRoot(document.getElementById('root')).render(<App/>);
