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
 const [tab,setTab]=useState('overview'),[req,setReq]=useState([]),[approved,setApproved]=useState([]),[directory,setDirectory]=useState([]),[sel,setSel]=useState(null),[note,setNote]=useState(''),[error,setError]=useState('');
 const token=account?.access_token,headers={Authorization:'Bearer '+token};
 async function load(){if(!token)return;try{setError('');const urls=['/v2/admin/verifications?status=submitted','/v2/admin/verifications?status=under_review','/v2/admin/verifications?status=approved','/admin/providers','/admin/summary'];const rs=await Promise.all(urls.map(u=>fetch(API+u,{headers})));if(rs.some(x=>!x.ok))throw Error('Admin data load failed');const d=await Promise.all(rs.map(x=>x.json()));setReq([...d[0],...d[1]]);setApproved(d[2]);setDirectory(d[3]);setSummary(d[4]);}catch(e){setError(e.message)}}
 const [summary,setSummary]=useState({});React.useEffect(()=>{load()},[]);
 async function act(id,status){try{const r=await fetch(API+'/v2/admin/verifications/'+id,{method:'PATCH',headers:{...headers,'Content-Type':'application/json'},body:JSON.stringify({status,admin_notes:note})});const d=await r.json();if(!r.ok)throw Error(d.detail||'Action failed');setSel(null);setNote('');load()}catch(e){setError(e.message)}}
 async function doc(id,type){const r=await fetch(API+'/v2/admin/verifications/'+id+'/document/'+type,{headers});if(!r.ok){setError('Document unavailable');return}window.open(URL.createObjectURL(await r.blob()),'_blank')}
 if(!account)return <LoginPortal kind="admin"/>;
 const nav=[['overview','Dashboard'],['requests','Business Requests'],['approved','Approved Businesses'],['directory','Business Directory']];
 const table=(data)=><div className="adm-tablewrap"><table className="adm-table"><thead><tr><th>BUSINESS</th><th>OWNER</th><th>EMAIL</th><th>PHONE</th><th>CATEGORY</th><th>LOCATION</th><th>STATUS</th><th></th></tr></thead><tbody>{data.map(b=><tr key={b.id}><td><b>{b.business_name||b.name}</b></td><td>{b.owner_name||'—'}</td><td>{b.owner_email||'—'}</td><td>{b.owner_phone||'—'}</td><td>{(b.categories||[b.category]).filter(Boolean).join(', ')}</td><td>{[b.locality,b.city].filter(Boolean).join(', ')}</td><td><span className="adm-status">{b.status||b.approval_status}</span></td><td><button className="adm-small" onClick={()=>setSel(b)}>View</button></td></tr>)}</tbody></table></div>;
 return <div className="adm-shell"><aside className="adm-sidebar"><div className="adm-brand"><span>✦</span><b>LUSHORA</b><small>ADMIN CONSOLE</small></div><p className="adm-navlabel">MENU</p>{nav.map(([k,l])=><button className={'adm-nav '+(tab===k?'active':'')} key={k} onClick={()=>{setTab(k);setSel(null)}}><span>{k==='overview'?'◫':k==='requests'?'◈':k==='approved'?'✓':'▤'}</span>{l}{k==='requests'&&req.length>0&&<em>{req.length}</em>}</button>)}<div className="adm-sidebottom"><div className="adm-avatar">A</div><div><b>Admin</b><small>{account.user?.email}</small></div><button onClick={()=>{localStorage.removeItem('lushora-admin');location.href='/admin/login'}}>Logout</button></div></aside><main className="adm-main"><header className="adm-top"><div><small>ADMIN / {tab.toUpperCase()}</small><h1>{nav.find(n=>n[0]===tab)?.[1]}</h1></div><button className="adm-refresh" onClick={load}>↻ Refresh</button></header>{error&&<p className="adm-error">{error}</p>}
 {tab==='overview'&&<><div className="adm-stats"><article><small>PROVIDER PROFILES</small><strong>{summary.providers||0}</strong><span>Business directory</span></article><article><small>PENDING REQUESTS</small><strong>{req.length}</strong><span>Admin review required</span></article><article><small>APPROVED</small><strong>{approved.length}</strong><span>Verified businesses</span></article><article><small>BOOKINGS</small><strong>{summary.bookings||0}</strong><span>{summary.requested_bookings||0} pending</span></article></div><section className="adm-panel"><div className="adm-panelhead"><div><h2>Recent requests</h2><p>Review businesses awaiting approval</p></div><button onClick={()=>setTab('requests')}>View all →</button></div>{table(req.slice(0,8))}</section></>}
 {tab==='requests'&&<section className="adm-panel"><div className="adm-panelhead"><div><h2>Business requests</h2><p>Submitted and under-review profiles</p></div><span>{req.length} requests</span></div>{table(req)}</section>}
 {tab==='approved'&&<section className="adm-panel"><div className="adm-panelhead"><div><h2>Approved businesses</h2><p>Approved verification profiles</p></div><span>{approved.length}</span></div>{table(approved)}</section>}
 {tab==='directory'&&<section className="adm-panel"><div className="adm-panelhead"><h2>Business directory</h2><span>{directory.length} providers</span></div>{table(directory)}</section>}
 {sel&&<div className="adm-modalback" onClick={()=>setSel(null)}><section className="adm-detail" onClick={e=>e.stopPropagation()}><button className="adm-close" onClick={()=>setSel(null)}>×</button><small>PROFILE REVIEW</small><h2>{sel.business_name||sel.name}</h2><div className="adm-detailgrid">{[['Owner',sel.owner_name],['Email',sel.owner_email],['Phone',sel.owner_phone],['Category',(sel.categories||[sel.category]).filter(Boolean).join(', ')],['City',sel.city],['Locality',sel.locality],['Address',sel.address],['Aadhaar last 4',sel.aadhaar_last4],['PAN',sel.pan_number],['Submitted',sel.submitted_at?new Date(sel.submitted_at).toLocaleString():'—']].map(([l,v])=><div key={l}><small>{l}</small><p>{v||'—'}</p></div>)}</div>{sel.documents&&<div className="adm-docs"><h3>Documents</h3>{[['aadhaar','Aadhaar'],['pan','PAN'],['business','Business proof']].map(([t,l])=><button key={t} disabled={!sel.documents[t]} onClick={()=>doc(sel.id,t)}>{l} {sel.documents[t]?'↗':'Missing'}</button>)}</div>}<label className="adm-notelabel">Admin notes<textarea value={note} onChange={e=>setNote(e.target.value)} placeholder="Review notes or rejection reason"/></label>{sel.status!=='approved'&&sel.status!=='rejected'&&<div className="adm-actions"><button onClick={()=>act(sel.id,'under_review')}>Under review</button><button className="approve" onClick={()=>act(sel.id,'approved')}>Approve</button><button className="reject" onClick={()=>act(sel.id,'rejected')}>Reject</button></div>}</section></div>}</main></div>
}
export default function PortalApp(){
 const path=location.pathname;
 if(path.startsWith('/business/onboarding')) return <BusinessVerificationForm/>;
 if(path.startsWith('/business')) return <BusinessDashboard/>;
 if(path.startsWith('/admin')) return <AdminDashboard/>;
 return <LoginPortal kind="customer"/>;
}
