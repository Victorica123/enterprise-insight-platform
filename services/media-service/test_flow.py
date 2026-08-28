import json
import urllib.request
import time

BASE = 'http://localhost:8080'

def request_json(url, data=None, headers=None, method=None):
    h = headers or {}
    if data is not None and isinstance(data, dict):
        data = json.dumps(data).encode('utf-8')
        h.setdefault('Content-Type', 'application/json')
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode('utf-8'))

def main():
    print("=" * 60)
    print("Step 1: 注册账号")
    print("=" * 60)
    r = request_json(f'{BASE}/api/auth/register', {'username': 'demo-user', 'password': 'demo123'})
    print(json.dumps(r, indent=2, ensure_ascii=False))

    print("\n" + "=" * 60)
    print("Step 2: 登录获取 Token")
    print("=" * 60)
    r = request_json(f'{BASE}/api/auth/login', {'username': 'demo-user', 'password': 'demo123'})
    print(json.dumps(r, indent=2, ensure_ascii=False))
    token = r['data']['token']

    print("\n" + "=" * 60)
    print("Step 3: 单文件上传视频")
    print("=" * 60)
    boundary = '----WebKitFormBoundary7MA4YWxk'
    with open('tmp/sample.mp4', 'rb') as f:
        file_bytes = f.read()
    body = (
        f'--{boundary}\r\n'.encode() +
        b'Content-Disposition: form-data; name="file"; filename="sample.mp4"\r\n' +
        b'Content-Type: video/mp4\r\n\r\n' +
        file_bytes +
        f'\r\n--{boundary}--\r\n'.encode()
    )
    h = {
        'Authorization': f'Bearer {token}',
        'Content-Type': f'multipart/form-data; boundary={boundary}'
    }
    req = urllib.request.Request(f'{BASE}/api/media/upload/file', data=body, headers=h)
    with urllib.request.urlopen(req, timeout=30) as resp:
        r = json.loads(resp.read().decode('utf-8'))
    print(json.dumps(r, indent=2, ensure_ascii=False))
    task_id = r['data']['taskId']

    print("\n" + "=" * 60)
    print("Step 4: 轮询任务状态")
    print("=" * 60)
    for i in range(20):
        r = request_json(f'{BASE}/api/workflow/tasks/{task_id}', headers={'Authorization': f'Bearer {token}'})
        status = r['data']['status']
        print(f"  轮询 {i+1}: status={status}")
        if status in ('COMPLETED', 'FAILED'):
            print("\n最终结果:")
            print(json.dumps(r, indent=2, ensure_ascii=False))
            break
        time.sleep(1)

if __name__ == '__main__':
    main()
