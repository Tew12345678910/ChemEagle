"""Benchmark pinned Cloud Worker prompts through HKUST, without deploying the Worker.
The snapshot is supplied explicitly; scoring and ground truth remain outside this runner.
"""
import argparse, base64, importlib.util, json, time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from dotenv import dotenv_values
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from efficient import atomic_json, BASE_URL


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--snapshot',type=Path,required=True)
    p.add_argument('--input-dir',type=Path,required=True)
    p.add_argument('--env-file',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--workers',type=int,default=4)
    p.add_argument('--max-spend-hkd',type=float,default=40)
    p.add_argument('--limit',type=int)
    args=p.parse_args()
    spec=importlib.util.spec_from_file_location('cloud_pipeline_snapshot',args.snapshot)
    pipeline=importlib.util.module_from_spec(spec);spec.loader.exec_module(pipeline)
    env=dotenv_values(args.env_file);key=env.get('NEW_API_KEY') or env.get('API_KEY')
    if not key:raise SystemExit('No HKUST key configured')
    headers={'api-key':key}
    def balance():
        r=requests.get(BASE_URL+'/balance',headers=headers,timeout=30);r.raise_for_status();return float(r.json()['credit'])
    started=balance()
    images=sorted(x.name for x in args.input_dir.glob('*.png'))
    if args.limit:images=images[:args.limit]
    data=json.loads(args.output.read_text()) if args.output.exists() else {'backend':'current-cloud-gemini-two-pass','images':images,'runs':[], 'model':'gemini-3.7-flash','cloud_commit':'88ebf7a2080a4ab3ab22c7101cf67e9c1de407e1','transport':'HKUST direct; pinned Worker payload/parser, not live deployed endpoint','image_resize':False}
    existing={r['image']:r for r in data['runs']}
    def process(name):
        start=time.monotonic(); usage_calls=[]
        try:
            image=(args.input_dir/name).read_bytes()
            if len(image)>5*1024*1024:raise ValueError('Image exceeds Worker 5MiB limit')
            source={'mime_type':'image/png','base64':base64.b64encode(image).decode()}
            def complete(payload):
                response=requests.post(BASE_URL+'/chat/completions',headers=headers,json=payload,timeout=300)
                if response.status_code==400 and 'response_format' in payload:
                    payload=dict(payload);payload.pop('response_format');response=requests.post(BASE_URL+'/chat/completions',headers=headers,json=payload,timeout=300)
                response.raise_for_status();body=response.json();usage_calls.append(body.get('usage',{}))
                return pipeline.parse_model_json(pipeline.extract_message_content(body))
            candidate=complete(pipeline.extraction_payload(data['model'],source))
            final=complete(pipeline.validation_payload(data['model'],source,candidate))
            run={'image':name,'exit_code':0,'result':{'results':[final],'meta':{'source_usage':usage_calls[0],'review':{'model':data['model'],'usage':usage_calls[1]},'validated':True}}}
        except Exception as exc:
            run={'image':name,'exit_code':1,'error':type(exc).__name__,'result':{'results':[],'meta':{'source_usage':usage_calls[0] if usage_calls else {},'review':{'model':data['model'],'usage':usage_calls[1] if len(usage_calls)>1 else {}}}}}
        run['wall_seconds']=time.monotonic()-start
        return run
    pending=[n for n in images if n not in existing]
    for offset in range(0,len(pending),args.workers):
        if started-balance()>=args.max_spend_hkd:
            print('Spend checkpoint reached',flush=True);break
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            for future in as_completed([pool.submit(process,n) for n in pending[offset:offset+args.workers]]):
                r=future.result();existing[r['image']]=r;data['runs']=[existing[n] for n in images if n in existing];atomic_json(args.output,data)
                print(f"{len(existing)}/{len(images)} {r['image']} status={r['exit_code']} {r['wall_seconds']:.1f}s",flush=True)
    data['status']='completed' if len(existing)==len(images) else 'checkpoint'
    data['balance_start_hkd']=started;data['balance_end_hkd']=balance();atomic_json(args.output,data)

if __name__=='__main__':main()
