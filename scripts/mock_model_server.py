"""TEST ONLY: deterministic local OpenAI-compatible server; no real inference."""
import argparse
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):
        pass
    def reply(self,payload,status=200):
        encoded=json.dumps(payload,ensure_ascii=False).encode()
        self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(encoded)));self.end_headers();self.wfile.write(encoded)
    def do_GET(self):
        if self.path=='/v1/models':self.reply({'data':[{'id':'mock-academic-test'},{'id':'mock-embedding-test'}]})
        else:self.reply({'error':'unknown endpoint'},404)
    def do_POST(self):
        try:
            size=int(self.headers.get('Content-Length','0'))
            if size>256*1024: return self.reply({'error':'too large'},413)
            payload=json.loads(self.rfile.read(size))
            if self.path=='/v1/embeddings':
                vectors=[]
                for index,text in enumerate(payload['input']):
                    text=text.casefold()
                    vector=[float('gradient' in text or '梯度' in text),float('probability' in text or '概率' in text),float('matrix' in text or '矩阵' in text),.1]
                    vectors.append({'index':index,'embedding':vector})
                return self.reply({'data':vectors})
            data=json.loads(payload['messages'][-1]['content'])
            source=data['evidence'][0]
            citations=[{'id':source['chunk_id'],'quote':source['text'][:120]}]
            if data.get('kind')=='flashcards':
                answer={'drafts':[{'front':f'复习知识点 {i+1}：资料描述了什么？','back':source['text'][:180],'topic':'模拟复习','citations':citations} for i in range(data['count'])]}
            elif data.get('kind')=='quiz':
                questions=[]
                for i in range(data['count']):
                    kind=data['question_kinds'][i%len(data['question_kinds'])]
                    questions.append({'kind':kind,'prompt':f'根据资料回答第 {i+1} 题','options':['依据资料','无关内容'] if kind in ('single','multiple') else [],'correct_indices':[0] if kind in ('single','multiple') else [],'answer':source['text'][:120],'explanation':'这是一道测试服务生成的模拟练习。','topic':'模拟复习','citations':citations})
                answer={'draft':{'title':'模拟资料练习','questions':questions}}
            else:
                answer={'answer':'根据资料，相关知识点如下。\n\n'+source['text'][:180]+'\n\n[1] 这是测试用 Mock Provider 的确定性回答，不代表真实模型推理。','citations':citations,'insufficient_evidence':False}
            self.reply({'choices':[{'message':{'content':json.dumps(answer,ensure_ascii=False)}}]})
        except (ValueError,KeyError,IndexError,TypeError):
            self.reply({'error':'invalid test request'},400)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=18765);args=parser.parse_args()
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
