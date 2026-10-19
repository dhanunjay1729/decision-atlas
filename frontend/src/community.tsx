import React, {useEffect, useRef, useState} from 'react';
import {Check, Copy, Link, Share2, ShieldCheck, Trash2} from 'lucide-react';
import type {Analysis} from './types';

export interface Allowance {
  limit: number | null;
  used: number;
  remaining: number | null;
  owner?: boolean;
  daily?: {available: boolean; resets_at: string};
}

async function api(path: string, body?: unknown, token?: string | null, method?: string) {
  const response = await fetch(path, {
    method: method ?? (body === undefined ? 'GET' : 'POST'),
    ...(body === undefined ? {} : {body: JSON.stringify(body)}),
    headers: {
      ...(body === undefined ? {} : {'Content-Type': 'application/json'}),
      ...(token ? {Authorization: 'Bearer ' + token} : {}),
    },
  });
  const data = await response.json();
  if (!response.ok) throw Error(typeof data.detail === 'string' ? data.detail : 'This action is unavailable. Please try later.');
  return data;
}

export function debateUrl(id: string) {
  const url = new URL('/', window.location.origin);
  url.searchParams.set('share', id);
  return url.toString();
}

export function featuredUrl(id: string) {
  const url = new URL('/', window.location.origin);
  url.searchParams.set('debate', id);
  return url.toString();
}

export function ShareLink({id, question}: {id: string; question: string}) {
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState('');
  const input = useRef<HTMLInputElement>(null);
  const url = debateUrl(id);
  async function copy() {
    setError('');
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
    } catch {
      input.current?.focus();
      input.current?.select();
      setError('Copy the selected link to share this debate.');
    }
  }
  return <div className="share-link">
    <label className="share-link-label" htmlFor={'share-' + id}><Link size={15}/> Public debate link</label>
    <div className="share-link-controls">
      <input ref={input} id={'share-' + id} aria-label="Public debate link" readOnly value={url} onFocus={e => e.currentTarget.select()}/>
      <button className="secondary-button" onClick={() => void copy()}>{copied ? <Check size={16}/> : <Copy size={16}/>} {copied ? 'Copied' : 'Copy link'}</button>
      {typeof navigator.share === 'function' && <button className="secondary-button" onClick={async () => {
        setError('');
        try {await navigator.share({title: 'Decision Atlas', text: question, url});}
        catch (error) {if (!(error instanceof Error) || error.name !== 'AbortError') setError('Use Copy link to share this debate.');}
      }}><Share2 size={16}/> Share</button>}
    </div>
    <span className="share-feedback" role="status">{error || (copied ? 'Link copied. Anyone with the link can read the public debate.' : 'Anyone with this link can read the public copy.')}</span>
  </div>;
}

export function ShareDebate({analysis, getToken, onShared}: {
  analysis: Analysis;
  getToken: () => Promise<string | null>;
  onShared: (id: string) => void;
}) {
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [shareId, setShareId] = useState(analysis.share_id ?? '');
  const [error, setError] = useState('');
  async function share() {
    setBusy(true);setError('');
    try {
      let entry;
      if (analysis.history_id) {
        const token = await getToken();
        if (!token) throw Error('Sign in to share a debate from your private history.');
        entry = await api('/api/history/' + encodeURIComponent(analysis.history_id) + '/share', {consent: true}, token);
      } else {
        entry = await api('/api/shares', {publish_token: analysis.publish_token, consent: true});
      }
      setShareId(entry.id);onShared(entry.id);
    } catch (error) {setError(error instanceof Error ? error.message : 'Could not share this debate.');}
    finally {setBusy(false);}
  }
  return <section className="publish-debate" aria-label="Share debate">
    <div className="share-heading"><Share2 size={19}/><h3>Share this debate</h3></div>
    {shareId ? <ShareLink id={shareId} question={analysis.question}/> : <>
      <p>Create an unlisted link for anyone you send it to. This does not add your debate to Featured debates. Your question, perspectives, arguments, claims, report, and source titles/links are visible to anyone with the link. Uploaded passages are excluded, but generated text may reveal details from them.</p>
      <label className="consent-row"><input type="checkbox" checked={consent} disabled={busy} onChange={e => setConsent(e.target.checked)}/>I have reviewed this debate and agree to make it accessible by link.</label>
      <button className="secondary-button" disabled={!consent || busy} onClick={() => void share()}><Link size={16}/>{busy ? 'Creating link…' : 'Create share link'}</button>
    </>}
    {error && <p className="error" role="alert">{error}</p>}
  </section>;
}

export function PublishDebate({analysis, getToken, onPublished}: {
  analysis: Analysis;getToken: () => Promise<string | null>;onPublished: () => void;
}) {
  const [consent,setConsent]=useState(false);
  const [busy,setBusy]=useState(false);
  const [published,setPublished]=useState(false);
  const [error,setError]=useState('');
  async function publish() {
    setBusy(true);setError('');
    try {
      if (analysis.history_id) {
        const token=await getToken();
        if (!token) throw Error('Sign in to publish from your private history.');
        await api('/api/history/'+encodeURIComponent(analysis.history_id)+'/publish',{consent:true},token);
      } else await api('/api/featured',{publish_token:analysis.publish_token,consent:true});
      setPublished(true);onPublished();
    } catch (error) {setError(error instanceof Error ? error.message : 'Could not publish this debate.');}
    finally {setBusy(false);}
  }
  return <section className="publish-debate" aria-label="Publish to Featured">
    <div className="share-heading"><h3>Publish to Featured debates</h3></div>
    {published ? <p role="status">Published to Featured debates.</p> : <>
      <p>Let visitors discover this debate in the public gallery. This is a separate choice from sharing a link. Your question, arguments, report, and source titles/links become public. Uploaded passages are excluded, but generated text may still reveal details from them.</p>
      <label className="consent-row"><input type="checkbox" checked={consent} disabled={busy} onChange={e=>setConsent(e.target.checked)}/>I agree to publish this debate in Featured debates.</label>
      <button className="secondary-button" disabled={!consent||busy} onClick={()=>void publish()}>{busy?'Publishing…':'Publish to Featured'}</button>
    </>}
    {error&&<p className="error" role="alert">{error}</p>}
  </section>;
}

interface Entry {
  id: string;
  question: string;
  perspectives: string[];
  published_at: number;
  likes: number;
  evidence_mode: string;
}

export function FeaturedDebates({onOpen, refresh, owner, getToken}: {
  getToken: () => Promise<string | null>;
  onOpen: (analysis: Analysis) => void;
  refresh: number;
  owner: boolean;
}) {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [pending, setPending] = useState('');
  const [deleteId, setDeleteId] = useState('');
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError('');
    api('/api/featured').then(data => {
      if (active) setEntries(Array.isArray(data) ? data : data.entries ?? []);
    }).catch(error => {if (active) setError(error.message);})
      .finally(() => {if (active) setLoading(false);});
    return () => {active = false;};
  }, [refresh]);
  useEffect(() => {if (!owner) setDeleteId('');}, [owner]);

  async function remove(entry: Entry) {
    setPending(entry.id);
    setError('');
    try {
      const token = await getToken();
      if (!token) throw Error('Sign in with your admin Google account to delete a featured debate.');
      await api('/api/featured/' + entry.id, undefined, token, 'DELETE');
      setEntries(current => current.filter(item => item.id !== entry.id));
      setDeleteId('');
      setNotice('Debate removed from Featured. Independently shared links are unchanged.');
    } catch (error) {setError(error instanceof Error ? error.message : 'Unable to delete debate.');}
    finally {setPending('');}
  }

  return <section className="featured-section">
    <div className="eyebrow">COMMUNITY PERSPECTIVES</div>
    <h1>Featured debates</h1>
    <p>Explore debates people chose to publish in the community gallery. Trending order combines likes and recency; these are AI-generated analyses, not endorsed conclusions.</p>
    {owner && <div className="admin-banner"><ShieldCheck size={19}/><div><strong>Admin controls enabled</strong><span>You can remove debates from this gallery. Independently shared links are unaffected.</span></div></div>}
    {notice && <p className="notice" role="status">{notice}</p>}
    {loading ? <p role="status">Loading debates…</p> : !entries.length && !error ? <div className="featured-empty"><h2>Room for the first perspective.</h2><p>Complete a debate in the studio, review it, and choose Publish to Featured to feature it here.</p></div> : <div className="featured-grid">
      {entries.map(entry => <article className="featured-card" key={entry.id}>
        <span className="eyebrow">{entry.evidence_mode === 'web' ? 'WEB EVIDENCE' : entry.evidence_mode === 'documents' ? 'DOCUMENT BASED' : 'MODEL KNOWLEDGE'}</span>
        <h2>{entry.question}</h2>
        <p>{entry.perspectives.join(' · ')}</p>
        <small>{new Date(entry.published_at * 1000).toLocaleDateString()} · {entry.likes} {entry.likes === 1 ? 'like' : 'likes'}</small>
        <div className="featured-actions">
          <button className="secondary-button" disabled={!!pending} onClick={async () => {
            setPending(entry.id); setError('');
            try {
              const data = await api('/api/featured/' + entry.id);
              onOpen({...data.analysis, mode: 'live', publish_token: undefined, public_id: entry.id, published: true});
            } catch (error) {setError(error instanceof Error ? error.message : 'Unable to open debate.');}
            finally {setPending('');}
          }}>Read debate</button>
          <button className="text-button" disabled={!!pending} aria-label={`Like debate: ${entry.question}`} onClick={async () => {
            setPending(entry.id); setError('');
            try {
              const data = await api('/api/featured/' + entry.id + '/like', {});
              setEntries(current => current.map(item => item.id === entry.id ? {...item, likes: data.likes} : item));
            } catch (error) {setError(error instanceof Error ? error.message : 'Unable to like debate.');}
            finally {setPending('');}
          }}>♡ Like</button>
        </div>
        {owner && <div className="admin-card-actions">
          {deleteId === entry.id ? <div className="delete-confirm" role="group" aria-label="Confirm public debate deletion">
            <p><strong>Delete this featured debate?</strong> This removes the Featured publication. The author's private debate and independently shared links are kept.</p>
            <div><button className="danger-button" disabled={!!pending} onClick={() => void remove(entry)}>{pending === entry.id ? 'Deleting…' : 'Delete debate'}</button><button className="secondary-button" autoFocus disabled={!!pending} onClick={() => setDeleteId('')}>Cancel</button></div>
          </div> : <button className="text-button danger-text" disabled={!!pending} onClick={() => setDeleteId(entry.id)}><Trash2 size={15}/> Delete from Featured</button>}
        </div>}
      </article>)}
    </div>}
    {error && <p role="alert" className="error">{error}</p>}
    <p className="helper">One like per network per debate. Ranking can be influenced by shared networks or VPNs.</p>
  </section>;
}
