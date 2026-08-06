//! tests.rs — Phase 15A-3a Desktop bridge / lifecycle 测试 (≥40)。
//!
//! 覆盖:
//! - critical path: launch → ready → Console 健康 → WebView 端口 → shutdown 清理
//! - 失败场景: runtime unavailable / crash / port conflict / permission failure /
//!   timeout / 非 JSON / failed 状态
//! - clean shutdown: stop 后无残留进程 + pid 文件清理
//!
//! fake runtime: python3 脚本模拟 factory-runtime CLI (start/stop/status/logs),
//! 行为经 FAKE_RUNTIME_* env 控制 — 通过 Bridge::with_env 注入子进程,
//! 不改进程全局环境 (测试可并行)。

use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command as ProcCmd;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Mutex;
use std::time::Duration;

use crate::runtime::{self, Bridge, BridgeError};
use crate::{
    error_html, html_escape, launch_flow, percent_encode, resolve_runtime_cmd, shutdown_flow,
};

/// 进程全局 env 锁: 仅 DESKTOP_RUNTIME_CMD 相关测试需要
/// (fake 行为经 Bridge::with_env, 不进全局 env)。
static ENV_LOCK: Mutex<()> = Mutex::new(());
static COUNTER: AtomicU64 = AtomicU64::new(0);

/// fake factory-runtime CLI (python3, 行为由 env 控制)。
const FAKE_RUNTIME: &str = r#"#!/usr/bin/env python3
import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--root', default=None)
parser.add_argument('--json', action='store_true', dest='json_out')
sub = parser.add_subparsers(dest='command', required=True)
for name in ('start', 'stop', 'status', 'logs'):
    sp = sub.add_parser(name)
    sp.add_argument('--json', action='store_true', dest='json_out', default=argparse.SUPPRESS)
args = parser.parse_args()

root = Path(args.root) if args.root else Path.cwd()
fail = os.environ.get('FAKE_RUNTIME_FAIL', '')
port = int(os.environ.get('FAKE_RUNTIME_PORT', '0') or '0')
state_file = root / 'config' / 'runtime_state.json'
logs_dir = root / 'logs'
VERSION = '0.0.0-fake'


def save(state):
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(state, ensure_ascii=False))


def load():
    try:
        if state_file.exists():
            return json.loads(state_file.read_text())
    except Exception:
        pass
    return {'status': 'idle', 'pid': None, 'port': None, 'version': VERSION,
            'started_at': None, 'stopped_at': None}


def status_dict():
    d = dict(load())
    d.update(core_alive=(root / 'config' / 'core.pid').exists(),
             console_alive=(root / 'config' / 'console.pid').exists(),
             core_exit_code=None, console_exit_code=None)
    return d


def emit(d):
    if args.json_out:
        print(json.dumps(d, ensure_ascii=False))
    else:
        print('status: %s' % d['status'])


def log_line(name, text):
    logs_dir.mkdir(parents=True, exist_ok=True)
    with open(logs_dir / name, 'a', encoding='utf-8') as fh:
        fh.write(text + '\n')


if os.environ.get('FAKE_RUNTIME_TRACE') == '1':
    (root / 'config').mkdir(parents=True, exist_ok=True)
    (root / 'config' / 'argv_trace.json').write_text(json.dumps(sys.argv, ensure_ascii=False))

if fail == 'exit':
    print('error: fake runtime exit failure', file=sys.stderr)
    sys.exit(1)
if fail == 'hang':
    time.sleep(3600)
    sys.exit(0)

if args.command == 'start':
    if fail == 'port_conflict':
        probe = socket.socket()
        try:
            probe.bind(('127.0.0.1', port or 8000))
        except OSError:
            print('error: [Errno 48] Address already in use (port %d)' % (port or 8000),
                  file=sys.stderr)
            sys.exit(1)
        probe.close()
    if fail == 'nojson':
        print('this is not json')
        sys.exit(0)
    if fail == 'status_failed':
        save({'status': 'failed', 'pid': None, 'port': None, 'version': VERSION,
              'started_at': None, 'stopped_at': None})
        emit(status_dict())
        sys.exit(0)
    if fail == 'crash_after_start':
        save({'status': 'ready', 'pid': 424242, 'port': port or 8123, 'version': VERSION,
              'started_at': '2026-08-07T00:00:00Z', 'stopped_at': None})
        emit(status_dict())
        sys.exit(1)
    if port == 0:
        probe = socket.socket()
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
        probe.close()
    save({'status': 'starting', 'pid': os.getpid(), 'port': port, 'version': VERSION,
          'started_at': '2026-08-07T00:00:00Z', 'stopped_at': None})
    if os.environ.get('FAKE_RUNTIME_NO_SERVER') != '1':
        code = ("import socket,signal\n"
                "signal.alarm(30)\n"
                "s=socket.socket();s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)\n"
                "s.bind(('127.0.0.1',%d));s.listen(8)\n"
                "while True:\n"
                " c,_=s.accept()\n"
                " r=b''\n"
                " while b'\\r\\n\\r\\n' not in r:\n"
                "  d=c.recv(4096)\n"
                "  if not d: break\n"
                "  r+=d\n"
                " c.sendall(b'HTTP/1.1 200 OK\\r\\nContent-Length: 2\\r\\nConnection: close\\r\\n\\r\\n{}')\n"
                " c.close()\n") % port
        proc = subprocess.Popen([sys.executable, '-c', code],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        (root / 'config').mkdir(parents=True, exist_ok=True)
        (root / 'config' / 'console.pid').write_text('%d\n' % proc.pid)
        # core.pid 复用同一进程 (fake 简化; 避免伪造 pid 撞上后续进程)
        (root / 'config' / 'core.pid').write_text('%d\n' % proc.pid)
        log_line('runtime.log', 'started fake runtime on port %d' % port)
        log_line('console.log', 'fake console listening on port %d' % port)
        log_line('core.log', 'fake core ready')
        for _ in range(40):
            try:
                c = socket.create_connection(('127.0.0.1', port), timeout=0.2)
                c.sendall(b'GET /api/dashboard HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n')
                resp = b''
                while True:
                    d = c.recv(4096)
                    if not d:
                        break
                    resp += d
                c.close()
                if b'200' in resp:
                    break
            except OSError:
                time.sleep(0.05)
    if os.environ.get('FAKE_RUNTIME_DELAY_READY'):
        delay = float(os.environ['FAKE_RUNTIME_DELAY_READY'])
        flip_code = ("import time,json\n"
                     "time.sleep(%r)\n"
                     "p=%r\n"
                     "with open(p+'/config/runtime_state.json') as fh: st=json.load(fh)\n"
                     "st['status']='ready'\n"
                     "with open(p+'/config/runtime_state.json','w') as fh: json.dump(st,fh)\n" % (delay, str(root)))
        subprocess.Popen([sys.executable, '-c', flip_code],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        emit(status_dict())
        sys.exit(0)
    save({'status': 'ready', 'pid': os.getpid(), 'port': port, 'version': VERSION,
          'started_at': '2026-08-07T00:00:00Z', 'stopped_at': None})
    emit(status_dict())
    sys.exit(0)

if args.command == 'stop':
    if fail == 'nojson':
        print('not json from stop')
        sys.exit(0)
    keep = fail == 'keep_pidfiles'
    for name in ('console', 'core'):
        p = root / 'config' / ('%s.pid' % name)
        if p.exists():
            try:
                os.kill(int(p.read_text().strip()), signal.SIGTERM)
            except (OSError, ValueError):
                pass
            if not keep:
                try:
                    p.unlink()
                except OSError:
                    pass
    st = load()
    st['status'] = 'stopped'
    st['stopped_at'] = '2026-08-07T00:00:00Z'
    save(st)
    log_line('runtime.log', 'stopped')
    emit(status_dict())
    sys.exit(0)

if args.command == 'status':
    if fail == 'nojson':
        print('not json from status')
        sys.exit(0)
    emit(status_dict())
    sys.exit(0)

if args.command == 'logs':
    out = {}
    for name in ('runtime.log', 'core.log', 'console.log'):
        p = logs_dir / name
        if p.exists():
            out[name] = p.read_text(errors='replace').splitlines()[-50:]
        else:
            out[name] = []
    if args.json_out:
        print(json.dumps({'root': str(root), 'files': out}, ensure_ascii=False))
    else:
        for name, lines in out.items():
            print('== %s ==' % name)
            for line in lines:
                print(line)
    sys.exit(0)

sys.exit(2)
"#;

// ---------------------------------------------------------------- 工具

struct TestDir(PathBuf);

impl TestDir {
    fn new(tag: &str) -> Self {
        let n = COUNTER.fetch_add(1, Ordering::Relaxed);
        let path =
            std::env::temp_dir().join(format!("desktop_15a3a_{tag}_{}_{n}", std::process::id()));
        let _ = fs::remove_dir_all(&path);
        fs::create_dir_all(&path).unwrap();
        TestDir(path)
    }

    fn path(&self) -> &Path {
        &self.0
    }

    /// 写可执行 fake runtime 脚本。
    fn fake_runtime(&self) -> PathBuf {
        let path = self.0.join("fake_runtime.py");
        fs::write(&path, FAKE_RUNTIME).unwrap();
        let mut perms = fs::metadata(&path).unwrap().permissions();
        std::os::unix::fs::PermissionsExt::set_mode(&mut perms, 0o755);
        fs::set_permissions(&path, perms).unwrap();
        path
    }
}

impl Drop for TestDir {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

/// 默认超时 bridge (fake + env)。
fn bridge_for(dir: &TestDir, envs: &[(&str, &str)]) -> Bridge {
    let fake = dir.fake_runtime();
    let mut b = Bridge::new(fake.to_string_lossy().into_owned());
    for (k, v) in envs {
        b = b.with_env(k, v);
    }
    b
}

/// 短超时 bridge (挂起/超时场景)。
fn fast_bridge_for(dir: &TestDir, envs: &[(&str, &str)]) -> Bridge {
    let fake = dir.fake_runtime();
    let mut b = Bridge::with_timeouts(
        fake.to_string_lossy().into_owned(),
        Duration::from_secs(2),
        Duration::from_secs(2),
        Duration::from_secs(2),
        Duration::from_secs(2),
    );
    for (k, v) in envs {
        b = b.with_env(k, v);
    }
    b
}

fn free_port() -> u16 {
    std::net::TcpListener::bind("127.0.0.1:0")
        .unwrap()
        .local_addr()
        .unwrap()
        .port()
}

fn pid_alive(pid: i32) -> bool {
    ProcCmd::new("kill")
        .args(["-0", &pid.to_string()])
        .status()
        .map(|s| s.success())
        .unwrap_or(false)
}

/// 杀 fake 后台进程 + 清 pid 文件 (防孤儿)。
fn cleanup_children(root: &Path) {
    for name in ["console", "core"] {
        let p = root.join("config").join(format!("{name}.pid"));
        if let Ok(text) = fs::read_to_string(&p) {
            if let Ok(pid) = text.trim().parse::<i32>() {
                let _ = ProcCmd::new("kill").args(["-9", &pid.to_string()]).status();
            }
        }
        let _ = fs::remove_file(&p);
    }
}

fn set_env(k: &str, v: &str) {
    std::env::set_var(k, v);
}
fn remove_env(k: &str) {
    std::env::remove_var(k);
}

/// 写 N 行日志文件。
fn write_lines(path: &Path, n: usize, prefix: &str) {
    let content: String = (0..n).map(|i| format!("{prefix}{i}\n")).collect();
    fs::write(path, content).unwrap();
}

// ================================================================ Bridge 构造

#[test]
fn bridge_new_custom_cmd() {
    let b = Bridge::new("/opt/fake/runtime");
    assert_eq!(b.cmd(), "/opt/fake/runtime");
}

#[test]
fn bridge_from_env_default() {
    let _g = ENV_LOCK.lock().unwrap();
    remove_env("DESKTOP_RUNTIME_CMD");
    assert_eq!(Bridge::from_env().cmd(), runtime::DEFAULT_RUNTIME_CMD);
}

#[test]
fn bridge_from_env_override() {
    let _g = ENV_LOCK.lock().unwrap();
    set_env("DESKTOP_RUNTIME_CMD", "/tmp/fake-runtime");
    assert_eq!(Bridge::from_env().cmd(), "/tmp/fake-runtime");
    set_env("DESKTOP_RUNTIME_CMD", "   ");
    assert_eq!(Bridge::from_env().cmd(), runtime::DEFAULT_RUNTIME_CMD);
    remove_env("DESKTOP_RUNTIME_CMD");
}

// ================================================================ parse_status

#[test]
fn parse_status_all_fields() {
    let st = runtime::parse_status(
        r#"{"status":"ready","pid":123,"port":8123,"version":"1.0.0",
           "started_at":"2026-08-07T00:00:00Z","stopped_at":null,
           "core_alive":true,"console_alive":true,
           "core_exit_code":null,"console_exit_code":0}"#,
    )
    .unwrap();
    assert_eq!(st.status, "ready");
    assert_eq!(st.pid, Some(123));
    assert_eq!(st.port, Some(8123));
    assert_eq!(st.version, "1.0.0");
    assert_eq!(st.started_at.as_deref(), Some("2026-08-07T00:00:00Z"));
    assert_eq!(st.stopped_at, None);
    assert!(st.core_alive);
    assert!(st.console_alive);
    assert_eq!(st.core_exit_code, None);
    assert_eq!(st.console_exit_code, Some(0));
    assert!(st.is_running());
}

#[test]
fn parse_status_missing_fields_defaults() {
    let st = runtime::parse_status(r#"{"status":"idle"}"#).unwrap();
    assert_eq!(st.status, "idle");
    assert_eq!(st.pid, None);
    assert_eq!(st.port, None);
    assert_eq!(st.version, "");
    assert!(!st.core_alive && !st.console_alive);
    assert!(!st.is_running());
}

#[test]
fn parse_status_null_values() {
    let st = runtime::parse_status(r#"{"status":"ready","pid":null,"port":null}"#).unwrap();
    assert_eq!(st.pid, None);
    assert_eq!(st.port, None);
    assert_eq!(st.status, "ready");
}

#[test]
fn parse_status_bad_json() {
    let e = runtime::parse_status("this is not json").unwrap_err();
    assert!(matches!(e, BridgeError::Parse(_)));
    assert!(e.to_string().contains("JSON"));
}

#[test]
fn parse_status_non_object() {
    assert!(matches!(
        runtime::parse_status("[1,2,3]").unwrap_err(),
        BridgeError::Parse(_)
    ));
    assert!(matches!(
        runtime::parse_status("42").unwrap_err(),
        BridgeError::Parse(_)
    ));
}

#[test]
fn parse_status_empty_object() {
    let st = runtime::parse_status("{}").unwrap();
    assert_eq!(st.status, "idle");
    assert_eq!(st.port, None);
}

#[test]
fn parse_status_port_out_of_range() {
    let st = runtime::parse_status(r#"{"status":"ready","port":70000}"#).unwrap();
    assert_eq!(st.port, None, "u16 溢出 → None (失败安全)");
}

// ================================================================ start

#[test]
fn start_success_ready_with_port() {
    let dir = TestDir::new("start_ok");
    let port = free_port();
    let b = bridge_for(&dir, &[("FAKE_RUNTIME_PORT", &port.to_string())]);
    let st = b.runtime_start(dir.path()).unwrap();
    assert_eq!(st.status, "ready");
    assert_eq!(st.port, Some(port));
    assert_eq!(st.version, "0.0.0-fake");
    assert!(st.console_alive);
    assert!(st.core_alive);
    cleanup_children(dir.path());
}

#[test]
fn start_argv_contains_root_start_json() {
    let dir = TestDir::new("start_argv");
    let b = bridge_for(&dir, &[("FAKE_RUNTIME_TRACE", "1")]);
    let root = dir.path();
    b.runtime_start(root).unwrap();
    let trace: serde_json::Value =
        serde_json::from_str(&fs::read_to_string(root.join("config/argv_trace.json")).unwrap())
            .unwrap();
    let args: Vec<&str> = trace
        .as_array()
        .unwrap()
        .iter()
        .map(|v| v.as_str().unwrap())
        .collect();
    assert!(args.contains(&"--root"));
    assert!(args.contains(&root.to_str().unwrap()));
    assert!(args.contains(&"start"));
    assert!(args.contains(&"--json"));
    cleanup_children(root);
}

#[test]
fn start_runtime_unavailable() {
    let dir = TestDir::new("start_missing");
    let b = Bridge::new("/nonexistent/factory-runtime-xyz");
    let e = b.runtime_start(dir.path()).unwrap_err();
    assert!(
        matches!(e, BridgeError::SpawnFailed(_)),
        "cmd 不存在 → SpawnFailed, got {e:?}"
    );
    assert!(e.to_string().contains("/nonexistent/factory-runtime-xyz"));
}

#[test]
fn start_crash_exit_code() {
    let dir = TestDir::new("start_exit");
    let b = bridge_for(&dir, &[("FAKE_RUNTIME_FAIL", "exit")]);
    let e = b.runtime_start(dir.path()).unwrap_err();
    match &e {
        BridgeError::Exit { code, stderr, .. } => {
            assert_eq!(*code, 1);
            assert!(stderr.contains("fake runtime exit failure"));
        }
        other => panic!("期望 Exit, got {other:?}"),
    }
    assert!(e.to_string().contains("exit=1"));
}

#[test]
fn start_crash_after_start_detected() {
    // 启动后 runtime 崩溃 (先打印 ready JSON 再非零退出) → 仍报错
    let dir = TestDir::new("start_crash_after");
    let b = bridge_for(&dir, &[("FAKE_RUNTIME_FAIL", "crash_after_start")]);
    let e = b.runtime_start(dir.path()).unwrap_err();
    assert!(
        matches!(e, BridgeError::Exit { code: 1, .. }),
        "非零退出必须报错, got {e:?}"
    );
}

#[test]
fn start_status_failed_error() {
    let dir = TestDir::new("start_failed");
    let b = bridge_for(&dir, &[("FAKE_RUNTIME_FAIL", "status_failed")]);
    let e = b.runtime_start(dir.path()).unwrap_err();
    assert!(
        matches!(e, BridgeError::RuntimeFailed(_)),
        "status=failed → RuntimeFailed, got {e:?}"
    );
}

#[test]
fn start_invalid_json_output() {
    let dir = TestDir::new("start_nojson");
    let b = bridge_for(&dir, &[("FAKE_RUNTIME_FAIL", "nojson")]);
    let e = b.runtime_start(dir.path()).unwrap_err();
    assert!(matches!(e, BridgeError::Parse(_)), "got {e:?}");
}

#[test]
fn start_timeout_kills_child() {
    let dir = TestDir::new("start_hang");
    let b = fast_bridge_for(&dir, &[("FAKE_RUNTIME_FAIL", "hang")]);
    let t0 = std::time::Instant::now();
    let e = b.runtime_start(dir.path()).unwrap_err();
    assert!(matches!(e, BridgeError::Timeout(_)), "got {e:?}");
    assert!(t0.elapsed() < Duration::from_secs(10), "超时应快速返回");
}

#[test]
fn start_port_conflict_error() {
    let dir = TestDir::new("start_conflict");
    let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
    let port = listener.local_addr().unwrap().port();
    let b = bridge_for(
        &dir,
        &[
            ("FAKE_RUNTIME_FAIL", "port_conflict"),
            ("FAKE_RUNTIME_PORT", &port.to_string()),
        ],
    );
    let e = b.runtime_start(dir.path()).unwrap_err();
    let msg = e.to_string();
    assert!(
        msg.contains("Address already in use") || msg.contains("port"),
        "port conflict 需提示端口占用, got: {msg}"
    );
    drop(listener);
}

#[test]
fn start_permission_data_root_is_file() {
    let dir = TestDir::new("start_rootfile");
    let file = dir.path().join("not_a_dir");
    fs::write(&file, "x").unwrap();
    let b = bridge_for(&dir, &[]);
    let e = b.runtime_start(&file).unwrap_err();
    assert!(matches!(e, BridgeError::DataRoot(_)), "got {e:?}");
    assert!(e.to_string().contains("不是目录"));
}

#[test]
fn start_permission_data_root_unwritable() {
    let dir = TestDir::new("start_nowrite");
    let locked = dir.path().join("locked");
    fs::create_dir_all(&locked).unwrap();
    let mut perms = fs::metadata(&locked).unwrap().permissions();
    std::os::unix::fs::PermissionsExt::set_mode(&mut perms, 0o000);
    fs::set_permissions(&locked, perms.clone()).unwrap();
    let b = bridge_for(&dir, &[]);
    let e = b.runtime_start(&locked).unwrap_err();
    std::os::unix::fs::PermissionsExt::set_mode(&mut perms, 0o700);
    fs::set_permissions(&locked, perms).unwrap();
    assert!(matches!(e, BridgeError::DataRoot(_)), "got {e:?}");
    assert!(e.to_string().contains("不可写"));
}

#[test]
fn start_creates_missing_data_root() {
    let dir = TestDir::new("start_mkdir");
    let root = dir.path().join("deep/root");
    let b = bridge_for(&dir, &[]);
    let st = b.runtime_start(&root).unwrap();
    assert_eq!(st.status, "ready");
    assert!(root.is_dir(), "data_root 应被创建");
    cleanup_children(&root);
}

// ================================================================ status

#[test]
fn status_idle_when_never_started() {
    let dir = TestDir::new("status_idle");
    let b = bridge_for(&dir, &[]);
    let st = b.runtime_status(dir.path()).unwrap();
    assert_eq!(st.status, "idle");
    assert_eq!(st.port, None);
}

#[test]
fn status_ready_after_start() {
    let dir = TestDir::new("status_ready");
    let b = bridge_for(&dir, &[]);
    b.runtime_start(dir.path()).unwrap();
    let st = b.runtime_status(dir.path()).unwrap();
    assert_eq!(st.status, "ready");
    assert!(st.console_alive);
    cleanup_children(dir.path());
}

#[test]
fn status_failed_detected() {
    let dir = TestDir::new("status_failed");
    let b_fail = bridge_for(&dir, &[("FAKE_RUNTIME_FAIL", "status_failed")]);
    let _ = b_fail.runtime_start(dir.path());
    let b = bridge_for(&dir, &[]);
    let st = b.runtime_status(dir.path()).unwrap();
    assert_eq!(st.status, "failed");
}

#[test]
fn status_command_failure() {
    let dir = TestDir::new("status_exit");
    let b = bridge_for(&dir, &[("FAKE_RUNTIME_FAIL", "exit")]);
    let e = b.runtime_status(dir.path()).unwrap_err();
    assert!(matches!(e, BridgeError::Exit { code: 1, .. }), "got {e:?}");
}

#[test]
fn status_invalid_json_output() {
    let dir = TestDir::new("status_nojson");
    let b = bridge_for(&dir, &[("FAKE_RUNTIME_FAIL", "nojson")]);
    let e = b.runtime_status(dir.path()).unwrap_err();
    assert!(matches!(e, BridgeError::Parse(_)), "got {e:?}");
}

// ================================================================ logs

#[test]
fn logs_reads_tail_all_files() {
    let dir = TestDir::new("logs_all");
    let logs = dir.path().join("logs");
    fs::create_dir_all(&logs).unwrap();
    write_lines(&logs.join("runtime.log"), 30, "runtime line ");
    write_lines(&logs.join("core.log"), 5, "core line ");
    fs::write(logs.join("console.log"), "").unwrap();
    let b = bridge_for(&dir, &[]);
    let bundle = b.runtime_logs(dir.path(), 50).unwrap();
    assert_eq!(bundle.runtime.len(), 30);
    assert_eq!(bundle.core.len(), 5);
    assert!(bundle.console.is_empty());
    assert_eq!(
        bundle.runtime.first().map(|s| s.as_str()),
        Some("runtime line 0")
    );
    assert_eq!(bundle.core.last().map(|s| s.as_str()), Some("core line 4"));
}

#[test]
fn logs_respects_lines_limit() {
    let dir = TestDir::new("logs_limit");
    let logs = dir.path().join("logs");
    fs::create_dir_all(&logs).unwrap();
    write_lines(&logs.join("runtime.log"), 100, "line ");
    let b = bridge_for(&dir, &[]);
    let bundle = b.runtime_logs(dir.path(), 10).unwrap();
    assert_eq!(bundle.runtime.len(), 10);
    assert_eq!(bundle.runtime.last().map(|s| s.as_str()), Some("line 99"));
}

#[test]
fn logs_missing_dir_is_empty() {
    let dir = TestDir::new("logs_missing");
    let b = bridge_for(&dir, &[]);
    let bundle = b.runtime_logs(dir.path(), 50).unwrap();
    assert!(bundle.is_empty());
    assert_eq!(bundle.runtime.len(), 0);
    assert_eq!(bundle.core.len(), 0);
    assert_eq!(bundle.console.len(), 0);
}

#[test]
fn logs_unreadable_file_error() {
    let dir = TestDir::new("logs_perm");
    let logs = dir.path().join("logs");
    fs::create_dir_all(&logs).unwrap();
    let core_log = logs.join("core.log");
    fs::write(&core_log, "secret\n").unwrap();
    let mut perms = fs::metadata(&core_log).unwrap().permissions();
    std::os::unix::fs::PermissionsExt::set_mode(&mut perms, 0o000);
    fs::set_permissions(&core_log, perms.clone()).unwrap();
    let b = bridge_for(&dir, &[]);
    let e = b.runtime_logs(dir.path(), 50).unwrap_err();
    std::os::unix::fs::PermissionsExt::set_mode(&mut perms, 0o600);
    fs::set_permissions(&core_log, perms).unwrap();
    assert!(matches!(e, BridgeError::DataRoot(_)), "got {e:?}");
    assert!(e.to_string().contains("读取日志"));
}

#[test]
fn logs_after_start_contains_lines() {
    let dir = TestDir::new("logs_after");
    let b = bridge_for(&dir, &[]);
    b.runtime_start(dir.path()).unwrap();
    let bundle = b.runtime_logs(dir.path(), 50).unwrap();
    assert!(
        bundle
            .runtime
            .iter()
            .any(|l| l.contains("started fake runtime")),
        "runtime.log 应含启动行, got {:?}",
        bundle.runtime
    );
    assert!(bundle.console.iter().any(|l| l.contains("listening")));
    cleanup_children(dir.path());
}

// ================================================================ stop / shutdown

#[test]
fn stop_returns_stopped() {
    let dir = TestDir::new("stop_ok");
    let b = bridge_for(&dir, &[]);
    b.runtime_start(dir.path()).unwrap();
    let st = b.runtime_stop(dir.path()).unwrap();
    assert_eq!(st.status, "stopped");
    assert!(!st.console_alive);
    cleanup_children(dir.path());
}

#[test]
fn stop_idempotent_when_idle() {
    let dir = TestDir::new("stop_idle");
    let b = bridge_for(&dir, &[]);
    let st = b.runtime_stop(dir.path()).unwrap();
    assert_eq!(st.status, "stopped");
}

#[test]
fn stop_failure_error() {
    let dir = TestDir::new("stop_fail");
    let b = bridge_for(&dir, &[("FAKE_RUNTIME_FAIL", "exit")]);
    let e = b.runtime_stop(dir.path()).unwrap_err();
    assert!(matches!(e, BridgeError::Exit { code: 1, .. }), "got {e:?}");
}

#[test]
fn stop_kills_child_and_removes_pid_files() {
    let dir = TestDir::new("stop_kill");
    let b = bridge_for(&dir, &[]);
    b.runtime_start(dir.path()).unwrap();
    let root = dir.path();
    let console_pid: i32 = fs::read_to_string(root.join("config/console.pid"))
        .unwrap()
        .trim()
        .parse()
        .unwrap();
    assert!(pid_alive(console_pid), "启动后 console 进程应存活");
    let st = b.runtime_stop(root).unwrap();
    assert_eq!(st.status, "stopped");
    // 等进程退出 (SIGTERM 异步)
    let deadline = std::time::Instant::now() + Duration::from_secs(3);
    while pid_alive(console_pid) && std::time::Instant::now() < deadline {
        std::thread::sleep(Duration::from_millis(50));
    }
    assert!(!pid_alive(console_pid), "stop 后 console 进程必须终止");
    assert!(
        !root.join("config/console.pid").exists(),
        "console.pid 应清理"
    );
    assert!(!root.join("config/core.pid").exists(), "core.pid 应清理");
}

#[test]
fn shutdown_flow_clean_after_launch() {
    // critical path: launch → ready → health → shutdown 清理
    let dir = TestDir::new("flow_clean");
    let port = free_port();
    let b = bridge_for(&dir, &[("FAKE_RUNTIME_PORT", &port.to_string())]);
    let launched = launch_flow(&b, dir.path(), Duration::from_secs(5)).unwrap();
    assert_eq!(launched.port, port);
    assert_eq!(launched.status.status, "ready");
    let root = dir.path();
    let console_pid: i32 = fs::read_to_string(root.join("config/console.pid"))
        .unwrap()
        .trim()
        .parse()
        .unwrap();
    let st = shutdown_flow(&b, root).unwrap();
    assert_eq!(st.status, "stopped");
    let deadline = std::time::Instant::now() + Duration::from_secs(3);
    while pid_alive(console_pid) && std::time::Instant::now() < deadline {
        std::thread::sleep(Duration::from_millis(50));
    }
    assert!(!pid_alive(console_pid), "clean shutdown: 无残留进程");
    assert!(!root.join("config/console.pid").exists());
    assert!(!root.join("config/core.pid").exists());
}

#[test]
fn shutdown_flow_idempotent_when_idle() {
    let dir = TestDir::new("flow_idle");
    let b = bridge_for(&dir, &[]);
    let st = shutdown_flow(&b, dir.path()).unwrap();
    assert_eq!(st.status, "stopped");
}

#[test]
fn shutdown_flow_detects_residual_pid_file() {
    let dir = TestDir::new("flow_residual");
    let b_launch = bridge_for(&dir, &[]);
    b_launch.runtime_start(dir.path()).unwrap();
    let root = dir.path();
    let _console_pid: i32 = fs::read_to_string(root.join("config/console.pid"))
        .unwrap()
        .trim()
        .parse()
        .unwrap();
    let b_residual = bridge_for(&dir, &[("FAKE_RUNTIME_FAIL", "keep_pidfiles")]);
    let e = shutdown_flow(&b_residual, root).unwrap_err();
    assert!(
        matches!(e, BridgeError::RuntimeFailed(_)),
        "stop 后残留 pid 文件必须报错, got {e:?}"
    );
    assert!(e.to_string().contains("残留"));
    // 手动清理 (真实服务器进程仍存活)
    cleanup_children(root);
}

#[test]
fn shutdown_flow_after_crash_state() {
    // runtime 崩溃后 (state=ready 但无 pid 文件) → stop 仍应成功归位
    let dir = TestDir::new("flow_crash");
    let b = bridge_for(&dir, &[("FAKE_RUNTIME_FAIL", "crash_after_start")]);
    let _ = b.runtime_start(dir.path());
    let b2 = bridge_for(&dir, &[]);
    let st = shutdown_flow(&b2, dir.path()).unwrap();
    assert_eq!(st.status, "stopped");
}

// ================================================================ launch_flow

#[test]
fn launch_flow_ready_health_ok() {
    let dir = TestDir::new("launch_ok");
    let port = free_port();
    let b = bridge_for(&dir, &[("FAKE_RUNTIME_PORT", &port.to_string())]);
    let launched = launch_flow(&b, dir.path(), Duration::from_secs(5)).unwrap();
    assert_eq!(launched.port, port);
    assert_eq!(launched.status.status, "ready");
    assert!(launched.status.console_alive);
    shutdown_flow(&b, dir.path()).unwrap();
}

#[test]
fn launch_flow_waits_for_ready() {
    let dir = TestDir::new("launch_delay");
    let b = bridge_for(
        &dir,
        &[
            ("FAKE_RUNTIME_DELAY_READY", "0.4"),
            ("FAKE_RUNTIME_PORT", &free_port().to_string()),
        ],
    );
    let launched = launch_flow(&b, dir.path(), Duration::from_secs(5)).unwrap();
    assert_eq!(launched.status.status, "ready", "应轮询至 ready");
    shutdown_flow(&b, dir.path()).unwrap();
}

#[test]
fn launch_flow_timeout_when_never_ready() {
    let dir = TestDir::new("launch_timeout");
    let b = bridge_for(
        &dir,
        &[
            ("FAKE_RUNTIME_DELAY_READY", "10"),
            ("FAKE_RUNTIME_PORT", &free_port().to_string()),
        ],
    );
    let e = launch_flow(&b, dir.path(), Duration::from_millis(1500)).unwrap_err();
    assert!(matches!(e, BridgeError::Timeout(_)), "got {e:?}");
    cleanup_children(dir.path());
}

#[test]
fn launch_flow_health_unreachable() {
    let dir = TestDir::new("launch_nohealth");
    let b = bridge_for(
        &dir,
        &[
            ("FAKE_RUNTIME_NO_SERVER", "1"),
            ("FAKE_RUNTIME_PORT", &free_port().to_string()),
        ],
    );
    let e = launch_flow(&b, dir.path(), Duration::from_secs(5)).unwrap_err();
    assert!(matches!(e, BridgeError::Health(_)), "got {e:?}");
    assert!(e.to_string().contains("/api/dashboard"));
    cleanup_children(dir.path());
}

#[test]
fn launch_flow_status_failed() {
    let dir = TestDir::new("launch_failed");
    let b = bridge_for(&dir, &[("FAKE_RUNTIME_FAIL", "status_failed")]);
    let e = launch_flow(&b, dir.path(), Duration::from_secs(5)).unwrap_err();
    assert!(matches!(e, BridgeError::RuntimeFailed(_)), "got {e:?}");
}

#[test]
fn launch_flow_missing_runtime_cmd() {
    let dir = TestDir::new("launch_missing");
    let b = Bridge::new("/nonexistent/factory-runtime");
    let e = launch_flow(&b, dir.path(), Duration::from_secs(5)).unwrap_err();
    assert!(matches!(e, BridgeError::SpawnFailed(_)), "got {e:?}");
}

#[test]
fn launch_flow_port_conflict() {
    let dir = TestDir::new("launch_conflict");
    let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
    let port = listener.local_addr().unwrap().port();
    let b = bridge_for(
        &dir,
        &[
            ("FAKE_RUNTIME_FAIL", "port_conflict"),
            ("FAKE_RUNTIME_PORT", &port.to_string()),
        ],
    );
    let e = launch_flow(&b, dir.path(), Duration::from_secs(5)).unwrap_err();
    let msg = e.to_string();
    assert!(
        msg.contains("Address already in use") || msg.contains("exit=1"),
        "port conflict 需上抛为错误, got: {msg}"
    );
    drop(listener);
}

#[test]
fn launch_flow_with_env_runtime_cmd() {
    let _g = ENV_LOCK.lock().unwrap();
    let dir = TestDir::new("launch_envcmd");
    let fake = dir.fake_runtime();
    set_env("DESKTOP_RUNTIME_CMD", fake.to_str().unwrap());
    assert_eq!(resolve_runtime_cmd(), fake.to_str().unwrap());
    let b = Bridge::from_env();
    let launched = launch_flow(&b, dir.path(), Duration::from_secs(5)).unwrap();
    assert_eq!(launched.status.status, "ready");
    shutdown_flow(&b, dir.path()).unwrap();
    remove_env("DESKTOP_RUNTIME_CMD");
}

// ================================================================ resolve / 工具

#[test]
fn resolve_runtime_cmd_default() {
    let _g = ENV_LOCK.lock().unwrap();
    remove_env("DESKTOP_RUNTIME_CMD");
    assert_eq!(resolve_runtime_cmd(), runtime::DEFAULT_RUNTIME_CMD);
}

#[test]
fn resolve_runtime_cmd_override() {
    let _g = ENV_LOCK.lock().unwrap();
    set_env("DESKTOP_RUNTIME_CMD", "/opt/factory-runtime/bin");
    assert_eq!(resolve_runtime_cmd(), "/opt/factory-runtime/bin");
    set_env("DESKTOP_RUNTIME_CMD", "");
    assert_eq!(resolve_runtime_cmd(), runtime::DEFAULT_RUNTIME_CMD);
    remove_env("DESKTOP_RUNTIME_CMD");
}

#[test]
fn percent_encode_keeps_unreserved() {
    assert_eq!(percent_encode("abc-123_.~"), "abc-123_.~");
}

#[test]
fn percent_encode_reserved_chars() {
    assert_eq!(percent_encode("a b&c<d#e"), "a%20b%26c%3Cd%23e");
}

#[test]
fn percent_encode_utf8() {
    assert_eq!(percent_encode("中文"), "%E4%B8%AD%E6%96%87");
}

#[test]
fn html_escape_basic() {
    assert_eq!(html_escape("a<b>&c"), "a&lt;b&gt;&amp;c");
}

#[test]
fn error_html_contains_escaped_message() {
    let html = error_html("boom <x> & y");
    assert!(
        html.contains("&lt;x&gt; &amp; y"),
        "消息必须转义, got: {html}"
    );
    assert!(html.contains("启动失败"));
}

#[test]
fn http_health_ok() {
    let dir = TestDir::new("health_ok");
    let port = free_port();
    let b = bridge_for(&dir, &[("FAKE_RUNTIME_PORT", &port.to_string())]);
    b.runtime_start(dir.path()).unwrap();
    assert!(runtime::http_health(port, Duration::from_secs(2)));
    cleanup_children(dir.path());
}

#[test]
fn http_health_refused() {
    let port = free_port();
    assert!(!runtime::http_health(port, Duration::from_millis(300)));
}

#[test]
fn read_tail_small_file() {
    let dir = TestDir::new("tail_small");
    let f = dir.path().join("f.log");
    write_lines(&f, 3, "l");
    let lines = runtime::read_tail(&f, 10).unwrap();
    assert_eq!(lines.len(), 3);
}

#[test]
fn runtime_status_is_running_helper() {
    let st = runtime::RuntimeStatus {
        status: "ready".into(),
        ..Default::default()
    };
    assert!(st.is_running());
    let st2 = runtime::RuntimeStatus {
        status: "idle".into(),
        ..Default::default()
    };
    assert!(!st2.is_running());
    let st3 = runtime::RuntimeStatus {
        status: "failed".into(),
        ..Default::default()
    };
    assert!(!st3.is_running());
}
