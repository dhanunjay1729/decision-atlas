import asyncio
import json
import math
import os
from pathlib import Path
from urllib.parse import urlparse
from .models import Source
from .providers import ProviderError

async def search(question, ledger):
    reservation=ledger.reserve(.018)
    process=None
    try:
        process=await asyncio.create_subprocess_exec('node',str(Path(__file__).resolve().parents[1]/'search.mjs'),stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL,env=os.environ.copy())
        output,_=await asyncio.wait_for(process.communicate(json.dumps({'question':question}).encode()),timeout=60)
        data=json.loads(output)
        if data.get('cost') is not None:
            cost=float(data['cost'])
            if not math.isfinite(cost) or cost<0:raise ValueError('Invalid cost')
            ledger.settle(reservation,cost)
        if process.returncode or data.get('search_calls')!=1:raise ValueError('Search failed')
        sources=[]
        for row in data.get('results',[])[:4]:
            url=row.get('url','');parsed=urlparse(url)
            if parsed.scheme not in ['http','https'] or not parsed.hostname or parsed.username or parsed.password:continue
            text=row.get('snippet','').strip()
            if not text:continue
            sources.append(Source(id='web'+str(len(sources)+1),title=row.get('title','Web excerpt')[:250],text=text[:4000],kind='web',url=url))
        if not sources:raise ValueError('No sources')
        return sources
    except (OSError,ValueError,asyncio.TimeoutError):
        raise ProviderError('Web search failed or returned no usable excerpts. Try later or turn off web search.',503) from None
    finally:
        if process and process.returncode is None:
            process.kill();await process.wait()
