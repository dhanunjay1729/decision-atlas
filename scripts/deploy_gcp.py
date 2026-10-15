"""Render a private Cloud Run deployment command. --apply is explicit opt-in.

Prerequisites and provisioning steps: docs/google-cloud.md.
No APIs, databases, IAM grants, secrets, or public access are created by default.
"""
import argparse,shlex,subprocess

def command(args):
    env=','.join(['MODEL_PROVIDER=vercel','LEDGER_BACKEND=firestore','TOTAL_MODEL_BUDGET_USD=2','MAX_DEBATES_PER_IP=5','MAX_RUNS_PER_IP_PER_HOUR=10','MAX_RUNS_PER_DAY=100','TRUSTED_PROXY_HOPS=0','GOOGLE_CLOUD_PROJECT='+args.project])
    return ['gcloud','run','deploy','decision-atlas','--project='+args.project,'--region='+args.region,'--image='+args.image,'--service-account='+args.service_account,'--port=8000','--cpu=1','--memory=512Mi','--timeout=600','--concurrency=2','--min-instances=0','--max-instances=1','--cpu-throttling','--no-allow-unauthenticated','--set-env-vars='+env,'--set-secrets=AI_GATEWAY_API_KEY='+args.secret+':'+args.secret_version]

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',required=True)
    parser.add_argument('--region',default='us-central1')
    parser.add_argument('--image',required=True,help='Reviewed, already-pushed image URL, preferably pinned to its digest')
    parser.add_argument('--service-account',required=True,help='Dedicated runtime account with only Firestore and secret access')
    parser.add_argument('--secret',default='atlas-gateway')
    parser.add_argument('--secret-version',default='1')
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    cmd=command(args)
    print(shlex.join(cmd))
    if args.apply:subprocess.run(cmd,check=True)
