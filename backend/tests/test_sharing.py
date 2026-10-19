"""Sharing has no gallery side effects and survives independent Featured removal."""
import json
from concurrent.futures import ThreadPoolExecutor
import pytest
from app.budget import Ledger
from app.featured import FeaturedError,create_store,_key
from app.sharing import create_sharing
from test_featured import FakeCloudLedger,analysis

@pytest.fixture(params=['sqlite','firestore'])
def stores(request,tmp_path):
    ledger=Ledger(str(tmp_path/'usage.sqlite3'))
    if request.param=='firestore':ledger=FakeCloudLedger(ledger)
    return create_store(tmp_path,ledger),create_sharing(tmp_path,ledger)

def test_share_and_featured_are_independent_in_both_directions(stores):
    featured,shares=stores
    data=analysis();token=featured.save_completed(data)
    for consent in (False,None,1,'true'):
        with pytest.raises(FeaturedError,match='consent'):shares.create(_key(token),data,consent)
    with ThreadPoolExecutor(max_workers=6) as pool:
        results=list(pool.map(lambda _:shares.create(_key(token),featured.completed(token),True),range(8)))
    shared=results[0]
    assert len({item['id'] for item in results})==1
    assert featured.list()==[]
    encoded=json.dumps(shared)
    assert 'PRIVATE_SOURCE_PASSAGE' not in encoded and 'publish_token' not in encoded
    assert 'private-model' not in encoded and 'voters' not in encoded
    publication=featured.publish(token,True)
    featured.vote(publication['id'],'192.0.2.1')
    featured.delete(publication['id'])
    assert featured.list()==[]
    later=shares.create('independent-later-share',featured.completed(token),True)
    assert shares.get(later['id'])==later
    assert shares.get(shared['id'])==shared
    assert shares.create(_key(token),data,True)==shared
    with pytest.raises(FeaturedError):featured.get(shared['id'])
    with pytest.raises(FeaturedError):shares.get(publication['id'])

def test_featured_publish_alone_never_creates_a_share(stores):
    featured,shares=stores
    publication=featured.publish(featured.save_completed(analysis()),True)
    assert shares._run(lambda tx:tx.get('state'))=={}
    with pytest.raises(FeaturedError):shares.get(publication['id'])

def test_share_limit_and_missing_links(stores,monkeypatch):
    import app.sharing as sharing
    _,shares=stores
    monkeypatch.setattr(sharing,'MAX_SHARES',1)
    shared=shares.create('first',analysis(),True)
    assert shares.create('first',analysis(),True)==shared
    with pytest.raises(FeaturedError,match='full'):shares.create('second',analysis(),True)
    for ident in ('invalid','0'*24):
        with pytest.raises(FeaturedError) as exc:shares.get(ident)
        assert exc.value.status_code==404

def test_routes_share_guest_and_owned_history_without_featuring(account_app,monkeypatch,tmp_path):
    import app.main as main
    import app.featured as featured
    client,ledger,provider=account_app
    shares=create_sharing(tmp_path,ledger)
    monkeypatch.setattr(main,'sharing_store',shares)
    data=analysis();token=main.featured_store.save_completed(data);data['publish_token']=token
    assert client.post('/api/shares',json={'publish_token':'forged','consent':True}).status_code==400
    assert client.post('/api/shares',json={'publish_token':token}).status_code==400
    response=client.post('/api/shares',json={'publish_token':token,'consent':True})
    assert response.status_code==200
    shared=response.json()
    ident=main.history_store.save_completed('signed-user-a',data)
    path='/api/history/'+ident+'/share'
    a={'Authorization':'Bearer signed-user-a'};b={'Authorization':'Bearer signed-user-b'}
    assert client.post(path,json={'consent':True}).status_code==401
    assert client.post(path,headers=b,json={'consent':True}).status_code==404
    assert client.post(path,headers=a,json={}).status_code==400
    now=featured.time.time()
    monkeypatch.setattr(featured.time,'time',lambda:now+featured.DRAFT_TTL+1)
    assert client.post(path,headers=a,json={'consent':True}).json()['id']==shared['id']
    assert client.get('/api/shares/'+shared['id']).status_code==200
    assert client.get('/api/featured').json()==[]
    assert client.get('/api/history/'+ident,headers=a).json()['analysis']['sources'][0]['text']=='PRIVATE_SOURCE_PASSAGE'
    assert provider.prompts==[]

# Reuse the isolated API fixture, never production credentials or inference.
from test_accounts import account_app
