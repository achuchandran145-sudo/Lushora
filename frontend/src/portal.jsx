import React, { useState } from 'react';
import './portal.css';

const API = import.meta.env.VITE_LUSHORA_API || 'http://127.0.0.1:8000/api';
const BRAND = 'LUSHORA';
const Logo = () => <div className="lux-logo"><span>✦</span><b>LUSHORA</b><small>BEAUTY · WELLNESS · SKIN</small></div>;

function LoginPortal({ kind }) {
  const [mode, setMode] = useState('login');
  const [phone, setPhone] = useState('');
  const [otp, setOtp] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [businessName, setBusinessName] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const isCustomer = kind === 'customer';
  const isAdmin = kind === 'admin';
  const title = isCustomer ? 'Your beauty journey begins here.' : isAdmin ? 'Platform control, with precision.' : 'Your business deserves to shine.';
  async function requestOtp() {
    setBusy(true); setNotice('');
    try {
      const r = await fetch(API + '/v2/customer/otp/request', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({phone})});
      const d=await r.json(); if(!r.ok) throw new Error(d.detail || 'OTP request failed');
      setNotice(d.message || 'OTP sent. Check your SMS.');
      if(d.development_otp) setOtp(d.development_otp);
      setMode('verify');
    } catch(e){setNotice(e.message)} finally{setBusy(false)}
  }
  async function verifyOtp() {
    setBusy(true);setNotice('');
    try {
      const r=await fetch(API+'/v2/customer/otp/verify',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({phone,otp})});
      const d=await r.json();if(!r.ok)throw new Error(d.detail||'OTP verification failed');
      localStorage.setItem('lushora-customer',JSON.stringify(d));localStorage.setItem('lushora-account',JSON.stringify(d));setNotice('Verified successfully. Welcome to LUSHORA.');
      window.location.href='/';
    }catch(e){setNotice(e.message)}finally{setBusy(false)}
  }
  async function loginBusiness(e) {
    e.preventDefault();setBusy(true);setNotice('');
    try {
      const endpoint=isAdmin?'/auth/login':'/auth/login';
      const payload={email,password};
      const r=await fetch(API+endpoint,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
      const d=await r.json();if(!r.ok)throw new Error(d.detail||'Login failed');
      const expected=isAdmin?'admin':'provider';
      if(d.user?.role!==expected)throw new Error('This account is not authorized for the '+expected+' portal.');
      localStorage.setItem(isAdmin?'lushora-admin':'lushora-business',JSON.stringify(d));
      window.location.href=isAdmin?'/admin':'/business';
    }catch(e){setNotice(e.message)}finally{setBusy(false)}
  }
  async function registerBusiness(e){
    e.preventDefault();setBusy(true);setNotice('');
    try{
      const r=await fetch(API+'/auth/register',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({full_name:businessName,email,phone,password,role:'provider'})});
      const d=await r.json();if(!r.ok)throw new Error(d.detail||'Registration failed');
      localStorage.setItem('lushora-business',JSON.stringify(d));setNotice('Account created. Continue to business profile onboarding.');window.location.href='/business/onboarding';
    }catch(e){setNotice(e.message)}finally{setBusy(false)}
  }
  return <main className="portal-shell">
    <aside className="portal-art"><div className="art-glow"/><div className="art-copy"><p className="portal-kicker">THE LUSHORA EXPERIENCE</p><h1>{title}</h1><p>{isCustomer?'Discover the finest beauty, wellness and skin experiences—curated around you.':isAdmin?'A thoughtfully designed command centre for the LUSHORA team.':'A refined space to manage your services, appointments and growth.'}</p><div className="art-line"/><span>CURATED BEAUTY · CONSIDERED WELLNESS</span></div></aside>
    <section className="portal-panel"><Logo/><div className="portal-form-wrap"><p className="portal-kicker">{isCustomer?'CUSTOMER ACCESS':isAdmin?'ADMINISTRATOR ACCESS':'BUSINESS PARTNER ACCESS'}</p><h2>{isCustomer?'Sign in with your mobile number':isAdmin?'Admin sign in':'Business sign in'}</h2><p className="portal-sub">{isCustomer?'We’ll send a one-time verification code to your phone.':'Use your registered credentials to access your secure portal.'}</p>
      {isCustomer ? <div className="portal-form">{mode==='verify'?<><label>Verification code<input value={otp} onChange={e=>setOtp(e.target.value)} inputMode="numeric" placeholder="Enter 6-digit OTP" maxLength={6}/></label><button disabled={busy||otp.length<4} onClick={verifyOtp}>{busy?'VERIFYING…':'VERIFY & CONTINUE'}</button><button className="portal-secondary" onClick={()=>setMode('phone')}>Change number</button></>:<><label>Mobile number<input value={phone} onChange={e=>setPhone(e.target.value)} inputMode="tel" placeholder="+91 98765 43210"/></label><button disabled={busy||phone.replace(/\D/g,'').length<10} onClick={requestOtp}>{busy?'SENDING…':'SEND OTP'}</button></>}</div>
      :<form className="portal-form" onSubmit={isAdmin||mode==='login'?loginBusiness:registerBusiness}>{mode==='register'&&!isAdmin&&<label>Owner name<input required value={businessName} onChange={e=>setBusinessName(e.target.value)} placeholder="Full name"/></label>}<label>Business / admin email<input required type="email" value={email} onChange={e=>setEmail(e.target.value)} placeholder="name@domain.com"/></label>{mode==='register'&&!isAdmin&&<label>Mobile number<input required value={phone} onChange={e=>setPhone(e.target.value)} placeholder="10-digit mobile number"/></label>}<label>Password<input required type="password" value={password} onChange={e=>setPassword(e.target.value)} placeholder="Password"/></label><button disabled={busy}>{busy?'PLEASE WAIT…':mode==='register'?'CREATE BUSINESS ACCOUNT':'SIGN IN'}</button>{!isAdmin&&<button type="button" className="portal-secondary" onClick={()=>setMode(mode==='login'?'register':'login')}>{mode==='login'?'Create a business account':'Back to business login'}</button>}</form>}
      {notice&&<div className="portal-notice">{notice}</div>}
      <div className="portal-foot">Secure access · Privacy-first · LUSHORA</div>{isCustomer&&<div className="portal-admin-entry"><a href="/admin/login">Admin Login</a></div>}
    </div></section>
  </main>
}


function BusinessVerificationForm(){
 const [account]=useState(()=>{try{return JSON.parse(localStorage.getItem('lushora-business')||'null')}catch{return null}});
 const [form,setForm]=useState({business_name:'',categories:[],city:'Coimbatore',locality:'',address:'',aadhaar_last4:'',pan_number:''});
 const [files,setFiles]=useState({aadhaar:null,pan:null,business:null});const [status,setStatus]=useState('');const [busy,setBusy]=useState(false);
 const api='http://127.0.0.1:8000/api';const token=account?.access_token;
 function set(k,v){setForm({...form,[k]:v})} function toggle(c){setForm({...form,categories:form.categories.includes(c)?form.categories.filter(x=>x!==c):[...form.categories,c]})}
 async function submit(e){e.preventDefault();if(!token){setStatus('Please log in again.');return}setBusy(true);setStatus('');try{const r=await fetch(api+'/v2/provider/verification/submit',{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+token},body:JSON.stringify(form)});const d=await r.json();if(!r.ok)throw new Error(d.detail||'Submission failed');for(const t of ['aadhaar','pan','business']){if(!files[t])throw new Error('Please select all three verification documents before submitting.');const fd=new FormData();fd.append('file',files[t]);const up=await fetch(api+'/v2/provider/verification/document/'+t,{method:'POST',headers:{Authorization:'Bearer '+token},body:fd});const ud=await up.json();if(!up.ok)throw new Error(ud.detail||'Document upload failed')}setStatus('Verification submitted. Your business is pending admin review.');}catch(e){setStatus(e.message)}finally{setBusy(false)}}
 return <div className="lux-dashboard"><header><Logo/><button onClick={()=>location.href='/business/login'}>Sign out</button></header><section className="dash-hero"><p className="portal-kicker">BUSINESS VERIFICATION</p><h1>Verify your business</h1><p>Your account is not listed publicly until Admin verifies your details and documents.</p></section><form className="verification-form" onSubmit={submit}><h2>Business details</h2><label>Business name<input required value={form.business_name} onChange={e=>set('business_name',e.target.value)}/></label><label>Categories (select all applicable)</label><div className="verification-categories">{['Makeup','Salon','Skin Clinic','Nail Studio'].map(c=><label key={c}><input type="checkbox" checked={form.categories.includes(c)} onChange={()=>toggle(c)}/>{c}</label>)}</div><label>City<input required value={form.city} onChange={e=>set('city',e.target.value)}/></label><label>Locality / Area<input required value={form.locality} onChange={e=>set('locality',e.target.value)}/></label><label>Full business address<textarea required value={form.address} onChange={e=>set('address',e.target.value)}/></label><h2>Identity verification</h2><label>Aadhaar last 4 digits only<input maxLength={4} inputMode="numeric" value={form.aadhaar_last4} onChange={e=>set('aadhaar_last4',e.target.value.replace(/\D/g,'').slice(0,4))}/></label><label>PAN number<input maxLength={10} value={form.pan_number} onChange={e=>set('pan_number',e.target.value.toUpperCase())}/></label><p className="verification-note">Do not enter your full Aadhaar number here. Upload document copies only for this test environment. Production storage must use encrypted private storage and a compliant verification process.</p>{[['aadhaar','Aadhaar document'],['pan','PAN document'],['business','Business proof (GST / registration / license)']].map(([key,label])=><label key={key}>{label}<input type="file" accept=".pdf,.jpg,.jpeg,.png" required onChange={e=>setFiles({...files,[key]:e.target.files?.[0]||null})}/></label>)}<button disabled={busy||!form.categories.length}>{busy?'SUBMITTING…':'SUBMIT FOR ADMIN VERIFICATION'}</button>{status&&<div className="portal-notice">{status}</div>}</form></div>
}

function BusinessDashboard(){
 const [account]=useState(()=>{try{return JSON.parse(localStorage.getItem('lushora-business')||'null')}catch{return null}});
 const [notice,setNotice]=useState('');
 if(!account)return <LoginPortal kind="business"/>;
 const user=account.user;
 return <div className="lux-dashboard"><header><Logo/><button onClick={()=>{localStorage.removeItem('lushora-business');location.href='/business/login'}}>Sign out</button></header><section className="dash-hero"><p className="portal-kicker">BUSINESS STUDIO</p><h1>Welcome back, {user?.full_name||'Partner'}.</h1><p>Manage your LUSHORA presence with care and clarity.</p></section><div className="dash-grid"><article><span>ACCOUNT</span><h3>{user?.email}</h3><p>Business account is ready for profile onboarding and verification.</p></article><article><span>YOUR NEXT STEP</span><h3>Complete your business profile</h3><p>Add your business name, location, services, pricing and operating hours.</p><button onClick={()=>location.href='/business/onboarding'}>Begin onboarding →</button></article><article><span>LEAD PROGRAM</span><h3>Area-based visibility</h3><p>Top 10 placements and subscription tiers will be managed by area and category after verification.</p></article></div>{notice&&<p>{notice}</p>}</div>
}
function AdminDashboard(){
 const [account]=useState(()=>{try{return JSON.parse(localStorage.getItem('lushora-admin')||'null')}catch{return null}});
 if(!account)return <LoginPortal kind="admin"/>;
 return <div className="lux-dashboard admin-dashboard"><header><Logo/><button onClick={()=>{localStorage.removeItem('lushora-admin');location.href='/admin/login'}}>Sign out</button></header><section className="dash-hero"><p className="portal-kicker">ADMIN COMMAND</p><h1>Platform overview</h1><p>Operations, providers, rankings, subscriptions and lead distribution.</p></section><div className="dash-grid"><article><span>PROVIDERS</span><h3>Verification & approvals</h3><p>Review submitted business credentials and approve eligible providers.</p></article><article><span>MARKETPLACE</span><h3>City · Area · Category</h3><p>Manage localities, categories, Top 10 rankings and subscription tiers.</p></article><article><span>LEAD ENGINE</span><h3>Sequential distribution</h3><p>Configure lead consent, rank order, 3-minute interval and lead delivery audit.</p></article><article><span>SECURITY</span><h3>Admin-only access</h3><p>Private admin accounts, role checks and platform-wide controls.</p></article></div></div>
}
export default function PortalApp(){
 const path=location.pathname;
 if(path.startsWith('/business/onboarding')) return <BusinessVerificationForm/>;
 if(path.startsWith('/business')) return <BusinessDashboard/>;
 if(path.startsWith('/admin')) return <AdminDashboard/>;
 return <LoginPortal kind="customer"/>;
}
