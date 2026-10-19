import React, {useCallback, useEffect, useRef, useState, useSyncExternalStore} from 'react';
import {getApp, getApps, initializeApp} from 'firebase/app';
import {createUserWithEmailAndPassword, GoogleAuthProvider, getAuth, onAuthStateChanged, onIdTokenChanged, sendPasswordResetEmail, signInWithEmailAndPassword, signInWithPopup, signOut, type Auth} from 'firebase/auth';
import type {Analysis} from './types';

type AccountUser={uid:string;email:string|null};
interface AccountSnapshot {user:AccountUser|null;loading:boolean;enabled:boolean;googleEnabled:boolean;error:string}
export interface Account extends AccountSnapshot {getToken:()=>Promise<string|null>}
let state:AccountSnapshot={user:null,loading:true,enabled:false,googleEnabled:false,error:''};
let auth:Auth|null=null;
let initialization:Promise<void>|null=null;
const subscribers=new Set<()=>void>();
function update(next:Partial<AccountSnapshot>){state={...state,...next};subscribers.forEach(listener=>listener());}
function subscribe(listener:()=>void){subscribers.add(listener);return()=>{subscribers.delete(listener);};}
function friendly(error:unknown):string{
 const code=typeof error==='object'&&error!==null&&'code' in error?String((error as {code:unknown}).code):'';
 if(['auth/invalid-email'].includes(code))return 'Enter a valid email address.';
 if(['auth/weak-password','auth/password-does-not-meet-requirements'].includes(code))return 'Choose a stronger password with at least 8 characters.';
 if(['auth/email-already-in-use','auth/invalid-credential','auth/wrong-password','auth/user-not-found'].includes(code))return 'Unable to sign in or create this account. Check your details, or reset your password.';
 if(code==='auth/popup-closed-by-user'||code==='auth/cancelled-popup-request')return 'Google sign-in was cancelled. You can try again when you are ready.';
 if(code==='auth/popup-blocked')return 'Your browser blocked the Google sign-in window. Allow pop-ups for this site, then try again.';
 if(code==='auth/account-exists-with-different-credential')return 'This email uses another sign-in method. Sign in with your existing method first.';
 if(code==='auth/too-many-requests')return 'Too many attempts. Please wait before trying again.';
 if(code==='auth/network-request-failed')return 'Could not reach sign-in services. Check your connection and try again.';
 if(code==='auth/user-disabled')return 'This account is unavailable. Please contact the site owner.';
 return 'Account services are unavailable right now. Please try again later.';
}
function initializeAccount(){
 if(initialization)return initialization;
 initialization=(async()=>{
  try{
   const response=await fetch('/api/auth/config');
   if(!response.ok)throw Error('config');
   const config=await response.json();
   if(!config.enabled){update({enabled:false,loading:false});return;}
   if(!config.apiKey||!config.authDomain||!config.projectId)throw Error('config');
   const name='decision-atlas-account';
   const app=getApps().some(app=>app.name===name)?getApp(name):initializeApp({apiKey:config.apiKey,authDomain:config.authDomain,projectId:config.projectId},name);
   auth=getAuth(app);
   update({enabled:true,googleEnabled:config.googleEnabled===true});
   const changed=()=>update({user:auth?.currentUser?{uid:auth.currentUser.uid,email:auth.currentUser.email}:null,loading:false,error:''});
   onAuthStateChanged(auth,changed,()=>update({user:null,loading:false,error:'Could not restore your session. Please sign in again.'}));
   // Firebase refreshes ID tokens; consumers obtain the current token for every API request.
   onIdTokenChanged(auth,changed,()=>update({error:'Your session needs attention. Please sign in again.'}));
  }catch{update({enabled:false,loading:false,error:'Account services are temporarily unavailable. You can still explore as a guest.'});}
 })();
 return initialization;
}
async function currentToken():Promise<string|null>{
 await initializeAccount();
 if(auth)await auth.authStateReady();
 const user=auth?.currentUser;
 if(!user)return null;
 try{
  const token=await user.getIdToken();
  if(auth?.currentUser?.uid!==user.uid)throw Error('Session changed');
  return token;
 }catch{throw Error('Your session expired. Please sign in again.');}
}
export function useAccount():Account{
 const snapshot=useSyncExternalStore(subscribe,()=>state,()=>state);
 useEffect(()=>{void initializeAccount();},[]);
 return {...snapshot,getToken:currentToken};
}

export function Accounts({account}:{account:Account}){
 const [mode,setMode]=useState<'login'|'signup'|'reset'>('login');
 const [email,setEmail]=useState('');const [password,setPassword]=useState('');
 const [busy,setBusy]=useState(false);const [error,setError]=useState('');const [notice,setNotice]=useState('');
 useEffect(()=>{setPassword('');setError('');setNotice('');},[account.user?.uid]);
 async function googleSignIn(){
  if(busy||!auth)return;
  setBusy(true);setError('');setNotice('');
  try{
   const provider=new GoogleAuthProvider();
   provider.setCustomParameters({prompt:'select_account'});
   await signInWithPopup(auth,provider);
   setPassword('');
  }catch(e){setError(friendly(e));}finally{setBusy(false);}
 }
 async function submit(event:React.FormEvent){
  event.preventDefault();if(busy||!auth)return;
  setBusy(true);setError('');setNotice('');
  try{
   if(mode==='reset'){
    await sendPasswordResetEmail(auth,email.trim());
    setNotice('If an account can receive a reset email, a link will arrive shortly. Check your spam folder too.');
   }else if(mode==='signup'){
    await createUserWithEmailAndPassword(auth,email.trim(),password);
    setPassword('');
   }else{await signInWithEmailAndPassword(auth,email.trim(),password);setPassword('');}
  }catch(e){setError(friendly(e));}finally{setBusy(false);}
 }
 if(account.loading)return <p className="helper" role="status">Restoring account…</p>;
 if(!account.enabled)return <p className="helper">{account.error||'Account sign-in is not enabled. You can use the studio as a guest.'}</p>;
 return <section className="account-panel" aria-label="Your account"><div className="eyebrow">YOUR WORKSPACE</div>{account.user?<><h2>Your account</h2><p>Signed in as <strong>{account.user.email||'your account'}</strong>.</p><p className="helper">Debates started while signed in are saved privately to My debates. Publishing to Featured debates is always a separate choice. Public accounts share the network allowance; eligible owner access is checked by the server.</p><button className="secondary-button" disabled={busy} onClick={async()=>{if(!auth)return;setBusy(true);setError('');try{await signOut(auth);}catch(e){setError(friendly(e));}finally{setBusy(false);}}}>Sign out</button></>:<><h2>{mode==='signup'?'Create an account':mode==='reset'?'Reset your password':'Welcome back'}</h2><p className="helper">You can start debates without an account. Signing in saves new completed debates to your private history.</p>{account.googleEnabled&&<><button type="button" className="secondary-button google-signin-button" disabled={busy} onClick={()=>void googleSignIn()}>{busy?'Please wait…':'Continue with Google'}</button><p className="helper">Or use an email and password below.</p></>}<form onSubmit={submit}><label className="field-label" htmlFor="account-email">Email</label><input id="account-email" type="email" autoComplete="email" required maxLength={254} value={email} disabled={busy} onChange={e=>setEmail(e.target.value)}/>{mode!=='reset'&&<><label className="field-label" htmlFor="account-password">Password</label><input id="account-password" type="password" required minLength={mode==='signup'?8:1} maxLength={256} autoComplete={mode==='signup'?'new-password':'current-password'} value={password} disabled={busy} onChange={e=>setPassword(e.target.value)}/></>}<button className="secondary-button" disabled={busy}>{busy?'Please wait…':mode==='signup'?'Create account':mode==='reset'?'Send reset link':'Sign in'}</button></form><div className="featured-actions">{mode!=='login'&&<button className="text-button" disabled={busy} onClick={()=>{setMode('login');setError('');setNotice('');setPassword('');}}>Sign in instead</button>}{mode!=='signup'&&<button className="text-button" disabled={busy} onClick={()=>{setMode('signup');setError('');setNotice('');setPassword('');}}>Create an account</button>}{mode!=='reset'&&<button className="text-button" disabled={busy} onClick={()=>{setMode('reset');setError('');setNotice('');setPassword('');}}>Forgot password?</button>}</div><p className="helper">Your password is handled directly by Firebase Authentication. Decision Atlas does not receive or store it.</p></>}{notice&&<p className="notice" role="status">{notice}</p>}{(error||account.error)&&<p className="error" role="alert">{error||account.error}</p>}</section>;
}

interface SavedDebate{id:string;question:string;perspectives:string[];created_at:number|string}
interface HistoryState{uid:string;entries:SavedDebate[];loading:boolean;error:string;hidden:SavedDebate|null}
export function MyDebates({getToken,onOpen,version}:{getToken:()=>Promise<string|null>;onOpen:(analysis:Analysis)=>void;version:number}){
 const account=useAccount();const uid=account.user?.uid||'';
 const [history,setHistory]=useState<HistoryState>({uid:'',entries:[],loading:true,error:'',hidden:null});
 const [pending,setPending]=useState('');const [reload,setReload]=useState(0);
 const identity=useRef(uid);identity.current=uid;
 const request=useCallback(async(path:string,body?:unknown,signal?:AbortSignal)=>{
  const startUid=identity.current;
  const token=await getToken();
  if(!token||!startUid||identity.current!==startUid)throw Error('Sign in to view your saved debates.');
  const response=await fetch(path,{signal,...(body===undefined?{}:{method:'POST',body:JSON.stringify(body)}),headers:{Authorization:'Bearer '+token,...(body===undefined?{}:{'Content-Type':'application/json'})}});
  const data=await response.json();
  if(identity.current!==startUid)throw Error('Your account changed. Please try again.');
  if(!response.ok)throw Error(response.status===401?'Your session expired. Please sign in again.':'Could not access your saved debates. Please try again.');
  return data;
 },[getToken]);
 useEffect(()=>{
  const controller=new AbortController();let active=true;
  setPending('');setHistory({uid,entries:[],loading:!!uid,error:'',hidden:null});
  if(uid)request('/api/history',undefined,controller.signal).then(data=>{if(active&&identity.current===uid)setHistory({uid,entries:Array.isArray(data)?data:data.entries??[],loading:false,error:'',hidden:null});}).catch(e=>{if(active&&!controller.signal.aborted&&identity.current===uid)setHistory({uid,entries:[],loading:false,error:e instanceof Error?e.message:'Could not load saved debates.',hidden:null});});
  return()=>{active=false;controller.abort();};
 },[uid,version,reload,request]);
 const visible=history.uid===uid?history:{uid,entries:[],loading:!!uid,error:'',hidden:null};
 async function changeHidden(entry:SavedDebate){
  const actionUid=uid;setPending(entry.id);
  try{await request('/api/history/'+encodeURIComponent(entry.id)+'/hide',{});if(identity.current!==actionUid)return;setHistory(current=>({...current,entries:current.entries.filter(item=>item.id!==entry.id),hidden:entry,error:''}));}
  catch(e){if(identity.current===actionUid)setHistory(current=>({...current,error:e instanceof Error?e.message:'Could not update history.'}));}
  finally{if(identity.current===actionUid)setPending('');}
 }
 return <section className="featured-section"><div className="eyebrow">PRIVATE WORKSPACE</div><h1>My debates</h1><p>Your saved debates are private. Share one publicly only when you choose to publish it.</p>{!uid?<p className="notice">Sign in to see your private history. The debate studio is open to guests too.</p>:visible.loading?<p role="status">Loading your debates…</p>:<>{visible.hidden&&<p className="notice" role="status">Debate hidden from your list. It remains retained privately; this does not delete its stored record.</p>}{!visible.entries.length&&!visible.error?<div className="featured-empty"><h2>Your next discussion starts here.</h2><p>Complete a debate while signed in and it will appear in this private workspace.</p></div>:<div className="featured-grid">{visible.entries.map(entry=><article className="featured-card" key={entry.id}><span className="eyebrow">PRIVATE DEBATE</span><h2>{entry.question}</h2><p>{entry.perspectives.join(' · ')}</p><small>{new Date(typeof entry.created_at==='number'?entry.created_at*1000:entry.created_at).toLocaleDateString()}</small><div className="featured-actions"><button className="secondary-button" disabled={!!pending} onClick={async()=>{const actionUid=uid;setPending(entry.id);try{const data=await request('/api/history/'+encodeURIComponent(entry.id));if(identity.current===actionUid)onOpen({...data.analysis,mode:'live',history_id:data.id});}catch(e){if(identity.current===actionUid)setHistory(current=>({...current,error:e instanceof Error?e.message:'Could not open debate.'}));}finally{if(identity.current===actionUid)setPending('');}}}>Open debate</button><button className="text-button" disabled={!!pending} onClick={()=>void changeHidden(entry)}>Hide from history</button></div></article>)}</div>}{visible.error&&<><p role="alert" className="error">{visible.error}</p><button className="secondary-button" onClick={()=>setReload(value=>value+1)}>Try again</button></>}</>}</section>;
}
