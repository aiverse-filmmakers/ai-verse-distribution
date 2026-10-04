from __future__ import annotations
import json, os, subprocess, tempfile, threading, time, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from agent_acceptance import run_cli, http_json, wait_http, stop_process, create_goal, write_acceptance_workspace, DEFAULT_AGENT_RELEASE, AGENT_RELEASE

TOKEN='distribution-runtime-acceptance-token-2026'; SECRET='test-upstream-secret'; PORT=18887
class Mock(BaseHTTPRequestHandler):
    seen=[]
    def do_POST(self):
        n=int(self.headers.get('content-length','0')); body=json.loads(self.rfile.read(n))
        Mock.seen.append((self.headers.get('authorization'),body))
        if body.get('messages',[{}])[-1].get('content')=='FAIL': self.send_response(500); self.end_headers(); self.wfile.write(b'upstream failure'); return
        if body.get('messages',[{}])[-1].get('content')=='TIMEOUT': time.sleep(3)
        tools = body.get('tools')
        msg={'role':'assistant','content':'mock runtime response'}
        out={'id':'mock-1','choices':[{'index':0,'message':msg,'finish_reason':'stop'}],'usage':{'prompt_tokens':11,'completion_tokens':7,'total_tokens':18}}
        raw=json.dumps(out).encode(); self.send_response(200); self.send_header('content-type','application/json'); self.send_header('content-length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
    def log_message(self,*a): pass

def main():
    base=Path(os.environ.get('RUNNER_TEMP') or tempfile.mkdtemp(prefix='aiverse-runtime-')); home=base/'home'; home.mkdir(parents=True); os.environ['HOME']=os.environ['USERPROFILE']=str(home); os.environ['AIVERSE_DISTRIBUTION_HOME']=str(base/'distribution'); os.environ['MODEL_API_KEY']=SECRET
    root=base/'system'; start=['start','--root',str(root)];
    if AGENT_RELEASE!=DEFAULT_AGENT_RELEASE: start += ['--release-set',AGENT_RELEASE]
    result=run_cli(*start); assert result.get('ready') is True, result
    install=json.loads((Path(os.environ['AIVERSE_DISTRIBUTION_HOME'])/'locks/current.json').read_text()); source=Path(install['components']['ai-verse-gateway']['source'])
    mock=ThreadingHTTPServer(('127.0.0.1',0),Mock); threading.Thread(target=mock.serve_forever,daemon=True).start()
    gateway_port=PORT
    setup=['node',str(source/'bin/aiverse-gateway.mjs'),'setup','--system-root',str(root),'--runtime','openai-compatible','--goal-owner-config',str(Path(os.environ['AIVERSE_DISTRIBUTION_HOME'])/'adapters/gateway-goal-owner.json'),'--base-url',f'http://127.0.0.1:{mock.server_port}','--model','mock-model','--api-key-env','MODEL_API_KEY','--token',TOKEN,'--port',str(gateway_port),'--json']
    out=subprocess.run(setup,text=True,capture_output=True,check=True); payload=json.loads(out.stdout); assert payload.get('runtime')=='openai-compatible'; assert payload.get('external_credentials_stored') is False
    write_acceptance_workspace(root)
    goal=create_goal(install,root)
    proc=subprocess.Popen(['node',str(source/'bin/aiverse-gateway.mjs'),'serve','--host','127.0.0.1','--port',str(gateway_port)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True); wait_http(f'http://127.0.0.1:{gateway_port}/health',token=TOKEN,process=proc)
    def call(content,tools=None,timeout=10):
        body={'model':'ignored-by-config','messages':[{'role':'user','content':content}], 'metadata':{'workspace_id':'alpha','goal_id':goal['goal_id'],'budget':{'max_tokens':2048,'max_actions':8}}, 'timeout_ms':60000};
        if tools: body['tools']=tools
        return http_json('POST',f'http://127.0.0.1:{gateway_port}/v1/chat/completions',body,token=TOKEN,timeout=timeout)
    try:
        normal=call('hello')
    except Exception:
        runs=Path(os.environ['HOME'])/'.aiverse/gateway/state/runs'; print('GATEWAY_DIAGNOSTIC', [p.read_text(errors='ignore') for p in runs.glob('*.json')])
        raise
    assert normal['choices'][0]['message']['content']=='mock runtime response' and normal['usage']['prompt_tokens']==11
    assert Mock.seen[-1][0]==f'Bearer {SECRET}' and Mock.seen[-1][1]['model']=='ignored-by-config'
    tool=call('hello',[{'type':'function','function':{'name':'mock_tool','parameters':{}}}]); assert any(row.get('function',{}).get('name')=='aiverse_action' for row in Mock.seen[-1][1].get('tools',[]))
    try: call('FAIL')
    except RuntimeError as e: assert '502' in str(e)
    else: raise AssertionError('upstream failure was not surfaced')
    stop_process(proc); write_acceptance_workspace(root)
    goal=create_goal(install,root)
    proc=subprocess.Popen(['node',str(source/'bin/aiverse-gateway.mjs'),'serve','--host','127.0.0.1','--port',str(gateway_port)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True); wait_http(f'http://127.0.0.1:{gateway_port}/health',token=TOKEN,process=proc); again=call('after restart'); assert again['choices'][0]['message']['content']=='mock runtime response'
    serialized='\n'.join(p.read_text(errors='ignore') for p in (home/'.aiverse').rglob('*') if p.is_file()); assert SECRET not in serialized
    stop_process(proc); mock.shutdown(); print(json.dumps({'ok':True,'runtime':'openai-compatible','restart_preserved':True,'tool_calls':True,'failure_mapping':True,'secret_not_persisted':True}))
if __name__=='__main__': main()
