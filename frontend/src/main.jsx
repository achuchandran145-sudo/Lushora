import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';
import PortalApp from './portal.jsx';

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
  const [categoriesSelected, setCategoriesSelected] = useState([]);
  const [city, setCity] = useState('All cities');
  const [search, setSearch] = useState('');
  const [verifiedOnly, setVerifiedOnly] = useState(false);
  const [notice, setNotice] = useState('');
  const [selected, setSelected] = useState(null);
  const [showAll, setShowAll] = useState(false);
  const [form, setForm] = useState({ name: '', phone: '', date: '' });
  const [slotDate,setSlotDate]=useState('');const [availableSlots,setAvailableSlots]=useState([]);const [slotsLoading,setSlotsLoading]=useState(false);const [selectedSlot,setSelectedSlot]=useState('');const [staffOptions,setStaffOptions]=useState([]);const [selectedStaffId,setSelectedStaffId]=useState('');
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);
  const [authMode, setAuthMode] = useState('login');
  const [authForm, setAuthForm] = useState({ full_name: '', email: '', phone: '', password: '', role: 'customer' });
  const [authOpen, setAuthOpen] = useState(false);
  const [businessOpen, setBusinessOpen] = useState(false);
  const [dashboardOpen, setDashboardOpen] = useState(false);
  const [dashboardData, setDashboardData] = useState(null);
  const [serviceForm, setServiceForm] = useState({ name: '', price_inr: '', duration_minutes: '30' });
  const [serviceEdit, setServiceEdit] = useState(null);
  const [rescheduleId,setRescheduleId]=useState(null);const [rescheduleValue,setRescheduleValue]=useState('');
  async function saveProviderService(serviceId,e){e.preventDefault();const fd=new FormData(e.currentTarget);try{const r=await fetch(API+'/provider/me/services/'+serviceId,{method:'PATCH',headers:{'Content-Type':'application/json',Authorization:'Bearer '+account.access_token},body:JSON.stringify({name:fd.get('name'),price_inr:Number(fd.get('price_inr')),duration_minutes:Number(fd.get('duration_minutes'))})});const data=await r.json();if(!r.ok)throw Error(data.detail||'Service update failed');setDashboardData(d=>({...d,provider:{...d.provider,services:d.provider.services.map(s=>s.id===serviceId?data:s)}}));setServiceEdit(null);setNotice('Service updated successfully.');}catch(err){setNotice(err.message)}}
  const [businessForm, setBusinessForm] = useState({ name: '', category: 'Salon', city: 'Coimbatore', locality: '', description: '' });
  const [account, setAccount] = useState(() => { try { return JSON.parse(localStorage.getItem('lushora-account') || 'null'); } catch { return null; } });

  async function load() {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (categoriesSelected.length) params.set('categories', categoriesSelected.join(','));
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
  useEffect(() => { load(); }, [categoriesSelected, city, verifiedOnly]);

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

  useEffect(()=>{if(!selected)return;setSelectedStaffId('');fetch(`${API}/providers/${selected.provider.id}/staff`).then(r=>r.ok?r.json():Promise.reject()).then(d=>setStaffOptions(d||[])).catch(()=>setStaffOptions([]))},[selected]);useEffect(()=>{if(!selected||!slotDate)return;setSlotsLoading(true);setSelectedSlot('');const staffQuery=selectedStaffId?'&staff_id='+selectedStaffId:'';fetch(`${API}/providers/${selected.provider.id}/available-slots?date=${slotDate}&service_id=${selected.service.id}${staffQuery}`).then(r=>r.ok?r.json():Promise.reject()).then(d=>setAvailableSlots(d.slots||[])).catch(()=>setAvailableSlots([])).finally(()=>setSlotsLoading(false))},[selected,slotDate,selectedStaffId]);

  async function joinWaitlist(){
    if(!account?.access_token){setNotice('Please sign in as a customer to join the waitlist.');setAuthOpen(true);return;}
    if(account.user?.role!=='customer'){setNotice('Waitlist is available to customer accounts.');return;}
    if(!slotDate){setNotice('Choose a preferred date first.');return;}
    try{const r=await fetch(API+'/customer/me/waitlist',{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+account.access_token},body:JSON.stringify({provider_id:selected.provider.id,service_id:selected.service.id,preferred_date:slotDate+'T00:00:00',preferred_time_start:selectedSlot||'',preferred_time_end:''})});const d=await r.json();if(!r.ok)throw new Error(d.detail||'Waitlist request failed');setNotice('You joined the waitlist. We will notify you when the booking process is updated.');}catch(err){setNotice(err.message)}
  }

  async function book(e) {
    e.preventDefault();
    if (!selected) return;
    try {
      const r = await fetch(`${API}/bookings`, { method: 'POST', headers: { 'Content-Type': 'application/json', ...(account?.access_token ? { Authorization: 'Bearer ' + account.access_token } : {}) }, body: JSON.stringify({ customer_name: form.name, customer_phone: form.phone, provider_id: selected.provider.id, service_id: selected.service.id, appointment_at: slotDate+'T'+selectedSlot+':00',staff_id:selectedStaffId?Number(selectedStaffId):null }) });
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
        const bookings=await r.json();const [nr,pr,rr,wl,pm]=await Promise.all([fetch(API+'/me/notifications',{headers}),fetch(API+'/me/notification-preferences',{headers}),fetch(API+'/customer/me/reviews',{headers}),fetch(API+'/customer/me/waitlist',{headers}),fetch(API+'/payments/me',{headers})]);setDashboardData({bookings,reviews:rr.ok?await rr.json():[],notifications:nr.ok?await nr.json():[],notificationPreferences:pr.ok?await pr.json():null,waitlist:wl.ok?await wl.json():[],payments:pm.ok?await pm.json():[]});
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
  async function updateNotificationPreference(field, value) {
    const current=dashboardData?.notificationPreferences;
    if(!current) return;
    const next={...current,[field]:value};
    setDashboardData(d=>({...d,notificationPreferences:next}));
    try {
      const r=await fetch(API+'/me/notification-preferences',{method:'PUT',headers:{'Content-Type':'application/json',Authorization:'Bearer '+account.access_token},body:JSON.stringify({[field]:value})});
      const data=await r.json();
      if(!r.ok) throw new Error(data.detail||'Could not update preferences');
      setDashboardData(d=>({...d,notificationPreferences:{...d.notificationPreferences,...data}}));
      setNotice('Notification preferences updated.');
    } catch(err) {
      setDashboardData(d=>({...d,notificationPreferences:current}));
      setNotice(err.message);
    }
  }

  async function createPaymentRecord(bookingId,paymentType){
    if(!account?.access_token){setNotice('Sign in to create a payment record.');return;}
    try{
      const key='lushora-'+bookingId+'-'+paymentType+'-'+Date.now();
      const r=await fetch(API+'/payments',{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+account.access_token,'Idempotency-Key':key},body:JSON.stringify({booking_id:bookingId,payment_type:paymentType})});
      const d=await r.json();if(!r.ok)throw Error(d.detail||'Payment request failed');
      if(!d.gateway_details){setNotice('Payment record #'+d.id+' created for ₹'+d.amount_inr+'. Gateway is not configured; no money was collected.');return;}
      if(!window.Razorpay){await new Promise((resolve,reject)=>{const script=document.createElement('script');script.src='https://checkout.razorpay.com/v1/checkout.js';script.onload=resolve;script.onerror=()=>reject(new Error('Could not load Razorpay Checkout'));document.body.appendChild(script);});}
      const opts={key:d.gateway_details.key_id,amount:d.gateway_details.amount,currency:d.gateway_details.currency,order_id:d.gateway_details.order_id,name:'LUSHORA',description:paymentType==='advance'?'20% booking advance':'Booking payment',prefill:{name:account.user?.full_name||'',contact:account.user?.phone||''},notes:{lushora_payment_id:String(d.id),booking_id:String(bookingId)},theme:{color:'#7c4d36'},handler:async response=>{try{const v=await fetch(API+'/payments/'+d.id+'/verify',{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+account.access_token},body:JSON.stringify(response)});const vd=await v.json();if(!v.ok)throw Error(vd.detail||'Payment verification failed');setNotice('Payment verified successfully. Reference '+response.razorpay_payment_id);await openDashboard();}catch(err){setNotice('Payment verification failed: '+err.message+' — do not retry blindly; check payment status.')}}};
      const checkout=new window.Razorpay(opts);checkout.on('payment.failed',response=>setNotice('Payment failed: '+(response.error?.description||'Please retry after checking status.')));checkout.open();
    }catch(err){setNotice(err.message)}
  }

  async function retryPaymentOrder(paymentId){
    try{const r=await fetch(API+'/payments/'+paymentId+'/retry-order',{method:'POST',headers:{Authorization:'Bearer '+account.access_token}});const d=await r.json();if(!r.ok)throw Error(d.detail||'Retry failed');const gd=d.gateway_details;if(!gd){setNotice(d.message||'Gateway not configured');return;}if(!window.Razorpay){await new Promise((resolve,reject)=>{const script=document.createElement('script');script.src='https://checkout.razorpay.com/v1/checkout.js';script.onload=resolve;script.onerror=()=>reject(new Error('Could not load Razorpay Checkout'));document.body.appendChild(script);});}const checkout=new window.Razorpay({key:gd.key_id,amount:gd.amount,currency:gd.currency,order_id:gd.order_id,name:'LUSHORA',description:'Payment retry',handler:async response=>{const v=await fetch(API+'/payments/'+paymentId+'/verify',{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+account.access_token},body:JSON.stringify(response)});const vd=await v.json();if(!v.ok)throw Error(vd.detail||'Verification failed');setNotice('Payment verified.');await openDashboard();}});checkout.open();}catch(e){setNotice(e.message)}
  }
  async function viewReceipt(paymentId){try{const r=await fetch(API+'/payments/'+paymentId+'/receipt',{headers:{Authorization:'Bearer '+account.access_token}});const d=await r.json();if(!r.ok)throw Error(d.detail||'Receipt unavailable');setNotice('Receipt '+d.receipt_number+' · '+d.provider_name+' · '+d.service_name+' · ₹'+d.amount_inr+' · '+d.status);}catch(e){setNotice(e.message)}}
  async function updateBookingStatus(id, status) {
    try {
      const r = await fetch(API + '/bookings/' + id + '/status?status=' + status, { method:'PATCH', headers:{ Authorization:'Bearer '+account.access_token } });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || 'Update failed');
      await openDashboard();
    } catch (err) { setNotice(err.message); }
  }
  async function submitReschedule(id) {
    try {
      const r=await fetch(API+'/bookings/'+id+'/reschedule',{method:'PATCH',headers:{'Content-Type':'application/json',Authorization:'Bearer '+account.access_token},body:JSON.stringify({appointment_at:rescheduleValue})});
      const d=await r.json();if(!r.ok)throw new Error(d.detail||'Reschedule failed');
      setRescheduleId(null);setRescheduleValue('');await openDashboard();setNotice('Booking rescheduled successfully.');
    } catch(err){setNotice(err.message)}
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
      <div className="header-actions"><button className="text-button" onClick={() => document.getElementById('business')?.scrollIntoView({ behavior: 'smooth' })}>List your business</button>{account && <button className="text-button" onClick={openDashboard}>Dashboard</button>}<button className="login-button" onClick={() => { if (account) { localStorage.removeItem('lushora-account'); setAccount(null); setNotice('You have signed out.'); } else { window.location.href = '/customer/login'; } }}>{account ? 'Sign out' : 'Log in'} <span>↗</span></button></div>
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
        <div className="category-list multi-category-list">{categories.filter(c=>c.key!=='All').map(c => <button type="button" key={c.key} className={`category-chip ${categoriesSelected.includes(c.key) ? 'active' : ''}`} onClick={() => { setCategoriesSelected(prev=>prev.includes(c.key)?prev.filter(x=>x!==c.key):[...prev,c.key]); setShowAll(false); }}><span>{categoriesSelected.includes(c.key)?'✓':c.icon}</span>{c.name}</button>)}</div><p className="category-selection-hint">Select one or more categories. Leave all unselected to explore everything.</p><button className="search-submit category-continue" onClick={()=>document.querySelector('.provider-section')?.scrollIntoView({behavior:'smooth'})}>Continue to results <span>→</span></button>
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

      <section className="business-banner" id="business"><div><p className="eyebrow light">FOR THE PEOPLE BEHIND THE BEAUTY</p><h2>Your craft deserves<br/><em>to be discovered.</em></h2><p>Bring your business to a community looking for their next favourite beauty experience.</p></div><button className="light-button" onClick={() => { window.location.href = '/business/login'; }}>List your business <span>↗</span></button></section>
    </main>

    <footer className="site-footer"><div className="footer-top"><a className="wordmark footer-wordmark" href="#top"><span className="mark">✿</span><span>LUSHORA</span></a><p>Discover beauty. Find your people. Make time for you.</p><div className="footer-links"><a href="#discover">Discover</a><a href="#journal">Journal</a><a href="#business">For businesses</a>{account?.user?.role==='customer'&&<a href="/customer/edit-profile">My Profile</a>}<a href="/admin/login">Admin Login</a></div></div><div className="footer-bottom"><span>© 2026 LUSHORA. All rights reserved.</span><span>BEAUTY · WELLNESS · SKIN CARE</span></div></footer>

    
    
    {dashboardOpen && <div className="modal-backdrop" onClick={()=>setDashboardOpen(false)}><div className="booking-modal dashboard-modal" onClick={e=>e.stopPropagation()}><button className="modal-close" onClick={()=>setDashboardOpen(false)}>×</button><p className="eyebrow">LUSHORA {account?.user?.role?.toUpperCase()} DASHBOARD</p><h2>{account?.user?.role==='admin'?'Platform overview':account?.user?.role==='provider'?'Business dashboard':'My bookings'}</h2>{dashboardData?.loading && <p>Loading dashboard…</p>}{dashboardData?.error && <p>{dashboardData.error}</p>}{dashboardData?.summary && <div className="dashboard-stats">{Object.entries(dashboardData.summary).map(([k,v])=><div key={k}><strong>{v}</strong><span>{k.replaceAll('_',' ')}</span></div>)}</div>}{dashboardData?.providers && account?.user?.role==='admin' && <><h3>Business approvals</h3>{dashboardData.providers.map(p=><div className="dashboard-row" key={p.id}><div><strong>{p.name}</strong><small>{p.city} · {p.category} · {p.approval_status}</small></div>{p.approval_status==='pending' && <div><button onClick={()=>approveProvider(p.id,'approved')}>Approve</button><button onClick={()=>approveProvider(p.id,'rejected')}>Reject</button></div>}</div>)}</>}{dashboardData?.provider && <div className="dashboard-provider"><h3>{dashboardData.provider.name}</h3><p>Status: {dashboardData.provider.approval_status}</p><p>{dashboardData.provider.services?.length || 0} services listed</p>{dashboardData?.provider?.approval_status==='approved' && <section className="provider-service-editor"><h3>Your services</h3>{(dashboardData.provider.services||[]).map(s=><article className="provider-service-item" key={s.id}><div className="provider-service-summary"><div><strong>{s.name}</strong><small>₹{s.price_inr} · {s.duration_minutes} minutes</small></div><button type="button" className="outline-button" onClick={()=>setServiceEdit(serviceEdit?.id===s.id?null:{id:s.id,name:s.name,price_inr:s.price_inr,duration_minutes:s.duration_minutes})}>{serviceEdit?.id===s.id?'Close':'Edit'}</button></div>{serviceEdit?.id===s.id&&<form className="service-edit-form" onSubmit={e=>saveProviderService(s.id,e)}><label>Name<input name="name" defaultValue={s.name} required minLength="2" maxLength="120"/></label><label>Price ₹<input name="price_inr" type="number" min="0" defaultValue={s.price_inr} required/></label><label>Duration<input name="duration_minutes" type="number" min="5" max="600" defaultValue={s.duration_minutes} required/></label><button className="dark-button">Save changes</button></form>}</article>)}</section>}{dashboardData?.provider?.approval_status==='approved' && <form className="service-add-form" onSubmit={addProviderService}><h3>Manage services</h3><label>Service name<input required value={serviceForm.name} onChange={e=>setServiceForm({...serviceForm,name:e.target.value})}/></label><label>Price (₹)<input type="number" min="0" required value={serviceForm.price_inr} onChange={e=>setServiceForm({...serviceForm,price_inr:e.target.value})}/></label><label>Duration (minutes)<input type="number" min="5" max="600" required value={serviceForm.duration_minutes} onChange={e=>setServiceForm({...serviceForm,duration_minutes:e.target.value})}/></label><button className="dark-button">Add service</button></form>}</div>}{dashboardData?.notificationPreferences && account?.user?.role==='customer' && <section className="notification-preferences"><div className="notification-pref-heading"><h3>Notification preferences</h3><p>Choose how LUSHORA can contact you about your bookings. External notifications are off until you opt in.</p></div>{[{key:'in_app_enabled',label:'In-app notifications',desc:'Updates inside your LUSHORA account'},{key:'push_enabled',label:'Push notifications',desc:'Browser or device notifications'},{key:'whatsapp_enabled',label:'WhatsApp',desc:'Booking updates via WhatsApp'},{key:'sms_enabled',label:'SMS',desc:'Text messages to your phone'}].map(item=><label className="notification-pref-row" key={item.key}><span><strong>{item.label}</strong><small>{item.desc}</small></span><input type="checkbox" checked={!!dashboardData.notificationPreferences[item.key]} onChange={e=>updateNotificationPreference(item.key,e.target.checked)}/></label>)}</section>}{dashboardData?.notifications && account?.user?.role==='customer' && <><h3>Notifications</h3>{dashboardData.notifications.map(n=><div className="dashboard-row" key={n.id}><div><strong>{n.title}</strong><small>{n.message} · {new Date(n.created_at).toLocaleString()}</small></div>{!n.is_read&&<button onClick={async()=>{await fetch(API+'/me/notifications/'+n.id+'/read',{method:'PATCH',headers:{Authorization:'Bearer '+account.access_token}});setDashboardData(d=>({...d,notifications:d.notifications.map(x=>x.id===n.id?{...x,is_read:true}:x)}))}}>Mark read</button>}</div>)}</>}{dashboardData?.bookings && account?.user?.role==='customer' && <section className="customer-review-section"><h3>Review completed appointments</h3>{dashboardData.bookings.filter(b=>b.status==='completed'&&!dashboardData.reviews?.some(r=>r.booking_id===b.id)).map(b=><form className="customer-review-form" key={b.id} onSubmit={async e=>{e.preventDefault();const fd=new FormData(e.currentTarget);try{const response=await fetch(API+'/customer/me/reviews',{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+account.access_token},body:JSON.stringify({booking_id:b.id,rating:Number(fd.get('rating')),comment:fd.get('comment')})});const data=await response.json();if(!response.ok)throw new Error(data.detail||'Review failed');setDashboardData(d=>({...d,reviews:[...(d.reviews||[]),data]}));}catch(err){setNotice(err.message)}}}><strong>Booking #{b.id}</strong><label>Rating<select name="rating" defaultValue="5"><option value="5">★★★★★ — Excellent</option><option value="4">★★★★ — Good</option><option value="3">★★★ — Average</option><option value="2">★★ — Poor</option><option value="1">★ — Very poor</option></select></label><label>Your review<textarea name="comment" maxLength="2000" placeholder="Share your experience (optional)"/></label><button type="submit">Submit review</button></form>)}{dashboardData.reviews?.length>0&&<div className="customer-review-list"><h4>Your submitted reviews</h4>{dashboardData.reviews.map(r=><article key={r.id}><strong>Booking #{r.booking_id} · {r.rating} ★ · {r.status}</strong><p>{r.comment||'No comment'}</p>{r.provider_reply&&<small>Business response: {r.provider_reply}</small>}</article>)}</div>}</section>}{account?.user?.role==='customer'&&<section className="customer-review-section"><h3>Your waitlist</h3>{!dashboardData.waitlist?.length&&<p>You have no waitlist entries.</p>}{dashboardData.waitlist?.map(w=><div className="dashboard-row" key={w.id}><div><strong>Waitlist #{w.id} · {w.status}</strong><small>Provider #{w.provider_id} · Service #{w.service_id} · {new Date(w.preferred_date).toLocaleDateString()} {w.preferred_time_start||'Any time'}</small></div>{w.status==='active'&&<button onClick={async()=>{try{const r=await fetch(API+'/customer/me/waitlist/'+w.id,{method:'DELETE',headers:{Authorization:'Bearer '+account.access_token}});const d=await r.json();if(!r.ok)throw Error(d.detail||'Cancel failed');setDashboardData(x=>({...x,waitlist:x.waitlist.map(z=>z.id===w.id?{...z,status:'cancelled'}:z)}));}catch(err){setNotice(err.message)}}}>Cancel waitlist</button>}</div>)}</section>}{dashboardData?.bookings && <><h3>Bookings</h3>{dashboardData.bookings.length===0 && <p>No bookings yet.</p>}{dashboardData.bookings.map(b=><div className="dashboard-row" key={b.id}><div><strong>Booking #{b.id} · {b.status}</strong><small>{new Date(b.appointment_at).toLocaleString()} · Service #{b.service_id}</small></div>{(account?.user?.role==='provider' || account?.user?.role==='admin') && b.status==='requested' && <div><button onClick={()=>updateBookingStatus(b.id,'confirmed')}>Confirm</button><button onClick={()=>updateBookingStatus(b.id,'rejected')}>Reject</button></div>}{['customer','provider'].includes(account?.user?.role) && ['requested','confirmed'].includes(b.status) && <button onClick={()=>{setRescheduleId(rescheduleId===b.id?null:b.id);setRescheduleValue('')}}>Reschedule</button>}{account?.user?.role==='customer'&&b.status==='confirmed'&&<div><button onClick={()=>createPaymentRecord(b.id,'full')}>Create full payment record</button><button onClick={()=>createPaymentRecord(b.id,'advance')}>Create 20% advance record</button></div>}{account?.user?.role==='customer' && ['requested','confirmed'].includes(b.status) && <button onClick={()=>updateBookingStatus(b.id,'cancelled')}>Cancel</button>}{rescheduleId===b.id&&<div className="dashboard-reschedule"><label>New appointment time<input type="datetime-local" step="1800" value={rescheduleValue} onChange={e=>setRescheduleValue(e.target.value)}/></label><button disabled={!rescheduleValue} onClick={()=>submitReschedule(b.id)}>Save new time</button><button onClick={()=>setRescheduleId(null)}>Close</button></div>}</div>)}</>}{account?.user?.role==='customer'&&dashboardData.payments&&<section className="customer-review-section"><h3>Payments</h3>{dashboardData.payments.length===0&&<p>No payment records.</p>}{dashboardData.payments.map(p=><div className="dashboard-row" key={p.id}><div><strong>Payment #{p.id} · {p.status}</strong><small>Booking #{p.booking_id} · ₹{p.amount_inr} · {p.payment_type} · Balance ₹{p.balance_due_inr}</small></div>{p.status==='failed'&&<button onClick={()=>retryPaymentOrder(p.id)}>Retry payment</button>}{['paid','partially_refunded','refunded'].includes(p.status)&&<button onClick={()=>viewReceipt(p.id)}>View receipt</button>}</div>)}</section>}</div></div>}

    {authOpen && <div className="modal-backdrop" onClick={() => setAuthOpen(false)}><form className="booking-modal account-modal" onSubmit={submitAuth} onClick={e=>e.stopPropagation()}><button type="button" className="modal-close" onClick={()=>setAuthOpen(false)}>×</button><p className="eyebrow">LUSHORA ACCOUNT</p><h2>{authMode === 'register' ? 'Create your account' : 'Welcome back'}</h2><div className="auth-switch"><button type="button" onClick={()=>setAuthMode('login')} className={authMode==='login'?'active':''}>Log in</button><button type="button" onClick={()=>setAuthMode('register')} className={authMode==='register'?'active':''}>Register</button></div>{authMode==='register' && <><label>Full name<input required minLength="2" value={authForm.full_name} onChange={e=>setAuthForm({...authForm,full_name:e.target.value})}/></label><label>Mobile number<input value={authForm.phone} onChange={e=>setAuthForm({...authForm,phone:e.target.value})} placeholder="Optional"/></label><label>Account type<select value={authForm.role} onChange={e=>setAuthForm({...authForm,role:e.target.value})}><option value="customer">Customer</option><option value="provider">Beauty business</option></select></label></>}<label>Email<input type="email" required value={authForm.email} onChange={e=>setAuthForm({...authForm,email:e.target.value})}/></label><label>Password<input type="password" required minLength="8" value={authForm.password} onChange={e=>setAuthForm({...authForm,password:e.target.value})}/></label><button className="dark-button full-button">{authMode==='register'?'Create account':'Log in'} <span>→</span></button></form></div>}
    {businessOpen && <div className="modal-backdrop" onClick={()=>setBusinessOpen(false)}><form className="booking-modal" onSubmit={submitBusiness} onClick={e=>e.stopPropagation()}><button type="button" className="modal-close" onClick={()=>setBusinessOpen(false)}>×</button><p className="eyebrow">JOIN THE LUSHORA EDIT</p><h2>List your business</h2><label>Business name<input required value={businessForm.name} onChange={e=>setBusinessForm({...businessForm,name:e.target.value})}/></label><label>Category<select value={businessForm.category} onChange={e=>setBusinessForm({...businessForm,category:e.target.value})}>{['Makeup','Salon','Skin Clinic','Nail Studio'].map(c=><option key={c}>{c}</option>)}</select></label><label>City<select value={businessForm.city} onChange={e=>setBusinessForm({...businessForm,city:e.target.value})}>{cityOptions.slice(1).map(c=><option key={c}>{c}</option>)}</select></label><label>Locality<input value={businessForm.locality} onChange={e=>setBusinessForm({...businessForm,locality:e.target.value})}/></label><label>About your business<textarea value={businessForm.description} onChange={e=>setBusinessForm({...businessForm,description:e.target.value})}/></label><button className="dark-button full-button">Submit for review <span>→</span></button><small className="booking-note">Business listings are reviewed before they appear publicly.</small></form></div>}

    {selected && <div className="modal-backdrop" onClick={() => setSelected(null)}><form className="booking-modal" onSubmit={book} onClick={e => e.stopPropagation()}><button type="button" className="modal-close" onClick={() => setSelected(null)}>×</button><p className="eyebrow">YOUR LUSHORA MOMENT</p><h2>{selected.service.name}</h2><p className="modal-provider">{selected.provider.name} · {selected.provider.locality}, {selected.provider.city}</p><div className="modal-price">₹{selected.service.price_inr}<span> · {selected.service.duration_minutes} minutes</span></div><label>Your name<input required minLength="2" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })}/></label><label>Mobile number<input required minLength="10" value={form.phone} onChange={e => setForm({ ...form, phone: e.target.value })} placeholder="10-digit mobile number"/></label><label>Appointment date<input required type="date" min={new Date().toISOString().slice(0,10)} value={slotDate} onChange={e=>setSlotDate(e.target.value)}/></label>{staffOptions.length>0&&<label>Preferred staff member<select value={selectedStaffId} onChange={e=>setSelectedStaffId(e.target.value)}><option value="">Any available staff</option>{staffOptions.map(st=><option key={st.id} value={st.id}>{st.full_name} · {st.role}</option>)}</select></label>}{slotDate&&<div className="available-slot-list"><p>{slotsLoading?'Checking available slots…':'Available time slots'}</p>{!slotsLoading&&availableSlots.length===0&&<small>No available slots for this date. Choose another date.</small>}{availableSlots.map(s=><button type="button" className={selectedSlot===s?'slot-selected':''} key={s} onClick={()=>setSelectedSlot(s)}>{s}</button>)}</div>}<input type="hidden" value={selectedSlot}/><button className="dark-button full-button" disabled={!selectedSlot}>Send booking request <span>→</span></button><button type="button" className="secondary-button full-button" onClick={joinWaitlist}>Join waitlist for this date</button><small className="booking-note">This preview creates a booking request. Availability is calculated from the business hours and existing bookings. Booking confirmation is still pending business approval.</small></form></div>}
  </>;
}

const portalPath = window.location.pathname;
createRoot(document.getElementById('root')).render(portalPath.startsWith('/customer') || portalPath.startsWith('/business') || portalPath.startsWith('/admin') ? <PortalApp/> : <App/>);
