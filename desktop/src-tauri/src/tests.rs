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

use crate::launcher::{friendly_error, status_label};
use crate::runtime::{self, Bridge, BridgeError};
use crate::{
    embedded_runtime_cmd, error_html, html_escape, launch_flow, percent_encode,
    resolve_runtime_cmd, resolve_runtime_cmd_at, shutdown_flow, RUNTIME_REMOTE_ENDPOINT_ENV,
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

// ================================================================ discovery
// Phase 15A-3c-2 Runtime Command Discovery:
//   env > embedded (resource_dir) > PATH; remote endpoint 扩展点 (预留)。
// 纯函数 (embedded_runtime_cmd / resolve_runtime_cmd_at) — 无需子进程。

/// 构造 resource_dir: 内嵌 bundle 可执行文件 (POSIX / Windows 名)。
fn embedded_dir(tag: &str, exe: &str) -> TestDir {
    let dir = TestDir::new(tag);
    let bundle = dir.path().join("factory-runtime-bundle");
    fs::create_dir_all(&bundle).unwrap();
    fs::write(bundle.join(exe), "#!/bin/sh\nexit 0\n").unwrap();
    dir
}

#[test]
fn embedded_runtime_cmd_detects_posix_bundle() {
    let dir = embedded_dir("emb_posix", "factory-runtime-bundle");
    let cmd = embedded_runtime_cmd(dir.path()).unwrap();
    assert!(cmd.ends_with("factory-runtime-bundle/factory-runtime-bundle"));
    assert!(Path::new(&cmd).is_file());
}

#[test]
fn embedded_runtime_cmd_detects_windows_bundle() {
    let dir = embedded_dir("emb_win", "factory-runtime-bundle.exe");
    let cmd = embedded_runtime_cmd(dir.path()).unwrap();
    assert!(cmd.ends_with("factory-runtime-bundle.exe"));
}

#[test]
fn embedded_runtime_cmd_prefers_posix_over_exe() {
    let dir = embedded_dir("emb_both", "factory-runtime-bundle");
    let bundle = dir.path().join("factory-runtime-bundle");
    fs::write(bundle.join("factory-runtime-bundle.exe"), "x").unwrap();
    let cmd = embedded_runtime_cmd(dir.path()).unwrap();
    assert!(!cmd.ends_with(".exe"), "POSIX 名优先, got: {cmd}");
}

#[test]
fn embedded_runtime_cmd_none_when_bundle_missing() {
    let dir = TestDir::new("emb_missing");
    assert_eq!(embedded_runtime_cmd(dir.path()), None);
}

#[test]
fn embedded_runtime_cmd_none_when_only_dir() {
    // bundle 目录存在但无可执行文件 (corrupted / 未打包) → None → 回退 PATH
    let dir = TestDir::new("emb_dironly");
    fs::create_dir_all(dir.path().join("factory-runtime-bundle")).unwrap();
    assert_eq!(embedded_runtime_cmd(dir.path()), None);
}

#[test]
fn resolve_runtime_cmd_at_embedded_preferred_over_path() {
    let _g = ENV_LOCK.lock().unwrap();
    remove_env("DESKTOP_RUNTIME_CMD");
    let dir = embedded_dir("disc_embedded", "factory-runtime-bundle");
    let cmd = resolve_runtime_cmd_at(Some(dir.path()));
    assert!(
        cmd.contains("factory-runtime-bundle"),
        "embedded 应优先于 PATH, got: {cmd}"
    );
}

#[test]
fn resolve_runtime_cmd_at_env_overrides_embedded() {
    let _g = ENV_LOCK.lock().unwrap();
    set_env("DESKTOP_RUNTIME_CMD", "/env/override/runtime");
    let dir = embedded_dir("disc_env", "factory-runtime-bundle");
    assert_eq!(
        resolve_runtime_cmd_at(Some(dir.path())),
        "/env/override/runtime",
        "env 是最高优先级 (测试注入/运维覆盖)"
    );
    remove_env("DESKTOP_RUNTIME_CMD");
}

#[test]
fn resolve_runtime_cmd_at_empty_env_falls_back_embedded() {
    let _g = ENV_LOCK.lock().unwrap();
    set_env("DESKTOP_RUNTIME_CMD", "   ");
    let dir = embedded_dir("disc_envblank", "factory-runtime-bundle");
    let cmd = resolve_runtime_cmd_at(Some(dir.path()));
    assert!(
        cmd.contains("factory-runtime-bundle"),
        "空 env → embedded, got: {cmd}"
    );
    remove_env("DESKTOP_RUNTIME_CMD");
}

#[test]
fn resolve_runtime_cmd_at_no_resource_dir_falls_back_path() {
    let _g = ENV_LOCK.lock().unwrap();
    remove_env("DESKTOP_RUNTIME_CMD");
    assert_eq!(resolve_runtime_cmd_at(None), runtime::DEFAULT_RUNTIME_CMD);
}

#[test]
fn resolve_runtime_cmd_at_resource_dir_without_bundle_falls_back_path() {
    let _g = ENV_LOCK.lock().unwrap();
    remove_env("DESKTOP_RUNTIME_CMD");
    let dir = TestDir::new("disc_emptydir");
    assert_eq!(
        resolve_runtime_cmd_at(Some(dir.path())),
        runtime::DEFAULT_RUNTIME_CMD
    );
}

#[test]
fn remote_endpoint_extension_point_reserved() {
    // Phase 16+ remote runtime 扩展点契约: env 名已预留, 解析链第 0 优先级
    assert_eq!(
        RUNTIME_REMOTE_ENDPOINT_ENV,
        "DESKTOP_RUNTIME_REMOTE_ENDPOINT"
    );
    // 未实现: 设置该 env 不影响当前解析 (Local Embedded 阶段)
    let _g = ENV_LOCK.lock().unwrap();
    remove_env("DESKTOP_RUNTIME_CMD");
    set_env(RUNTIME_REMOTE_ENDPOINT_ENV, "https://runtime.example.com");
    let dir = TestDir::new("disc_remote");
    assert_eq!(
        resolve_runtime_cmd_at(Some(dir.path())),
        runtime::DEFAULT_RUNTIME_CMD,
        "remote 未实现 → 不改变 Local 解析"
    );
    remove_env(RUNTIME_REMOTE_ENDPOINT_ENV);
}

#[test]
fn embedded_runtime_detected_then_missing_spawn_friendly() {
    // discovery 解析到 embedded 路径, 但可执行文件被删 (corrupted bundle)
    // → spawn 报友好错误 (含路径), 不 panic
    let dir = embedded_dir("disc_corrupt", "factory-runtime-bundle");
    let cmd = embedded_runtime_cmd(dir.path()).unwrap();
    fs::remove_file(&cmd).unwrap();
    let b = Bridge::new(cmd.clone());
    let e = b.runtime_status(dir.path()).unwrap_err();
    assert!(
        matches!(e, BridgeError::SpawnFailed(_)),
        "corrupted bundle → SpawnFailed, got {e:?}"
    );
    assert!(e.to_string().contains("factory-runtime-bundle"));
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

// ================================================================ 15A-3b
// runtime_restart (stop+start 组合)
// ================================================================

#[test]
fn restart_returns_ready_with_port() {
    let dir = TestDir::new("restart_ok");
    let port = free_port();
    let b = bridge_for(&dir, &[("FAKE_RUNTIME_PORT", &port.to_string())]);
    let st = b.runtime_restart(dir.path()).unwrap();
    assert_eq!(st.status, "ready");
    assert_eq!(st.port, Some(port));
    assert!(st.console_alive && st.core_alive);
    cleanup_children(dir.path());
}

#[test]
fn restart_stops_old_process_then_starts() {
    // 组合语义: stop 终止旧 server (SIGTERM) → start 起新 server 且健康
    let dir = TestDir::new("restart_seq");
    let port = free_port();
    let b = bridge_for(&dir, &[("FAKE_RUNTIME_PORT", &port.to_string())]);
    b.runtime_start(dir.path()).unwrap();
    let root = dir.path();
    let old_pid: i32 = fs::read_to_string(root.join("config/console.pid"))
        .unwrap()
        .trim()
        .parse()
        .unwrap();
    assert!(pid_alive(old_pid), "restart 前旧进程应存活");
    let st = b.runtime_restart(root).unwrap();
    assert_eq!(st.status, "ready");
    assert!(
        runtime::http_health(port, Duration::from_secs(2)),
        "restart 后 Console 应健康可达"
    );
    let deadline = std::time::Instant::now() + Duration::from_secs(3);
    while pid_alive(old_pid) && std::time::Instant::now() < deadline {
        std::thread::sleep(Duration::from_millis(50));
    }
    assert!(!pid_alive(old_pid), "restart 应终止旧进程");
    cleanup_children(root);
}

#[test]
fn restart_recovers_from_failed() {
    // start 进入 failed → restart (stop 归位 + start) → ready
    let dir = TestDir::new("restart_failed");
    let b_fail = bridge_for(&dir, &[("FAKE_RUNTIME_FAIL", "status_failed")]);
    let e = b_fail.runtime_start(dir.path()).unwrap_err();
    assert!(
        matches!(e, BridgeError::RuntimeFailed(_)),
        "前置: start 应 failed"
    );
    let b = bridge_for(&dir, &[]);
    let st = b.runtime_restart(dir.path()).unwrap();
    assert_eq!(st.status, "ready");
    assert!(st.console_alive);
    cleanup_children(dir.path());
}

#[test]
fn restart_when_idle_ok() {
    let dir = TestDir::new("restart_idle");
    let b = bridge_for(&dir, &[]);
    let st = b.runtime_restart(dir.path()).unwrap();
    assert_eq!(st.status, "ready");
    cleanup_children(dir.path());
}

#[test]
fn restart_failure_propagates() {
    let dir = TestDir::new("restart_exit");
    let b = bridge_for(&dir, &[("FAKE_RUNTIME_FAIL", "exit")]);
    let e = b.runtime_restart(dir.path()).unwrap_err();
    assert!(matches!(e, BridgeError::Exit { code: 1, .. }), "got {e:?}");
}

// ================================================================ 15A-3b
// health_detail 解析 (fake status JSON)
// ================================================================

/// 构造 RuntimeStatus (测试 helper)。
fn status_with(status: &str, core: bool, console: bool) -> runtime::RuntimeStatus {
    runtime::RuntimeStatus {
        status: status.into(),
        version: "1.2.3".into(),
        port: Some(8123),
        core_alive: core,
        console_alive: console,
        started_at: Some("2026-08-07T00:00:00Z".into()),
        ..Default::default()
    }
}

#[test]
fn health_detail_ready_all_ok() {
    let hd = runtime::health_detail(&status_with("ready", true, true));
    assert!(hd.overall);
    assert_eq!(hd.version, "1.2.3");
    assert_eq!(hd.port, Some(8123));
    assert!(hd.uptime_secs.is_some());
    assert_eq!(hd.components.len(), 3);
    assert!(hd.components.iter().all(|c| c.ok));
}

#[test]
fn health_detail_runtime_failed() {
    let hd = runtime::health_detail(&status_with("failed", false, false));
    assert!(!hd.overall);
    let rt = &hd.components[0];
    assert_eq!(rt.name, "Runtime");
    assert!(!rt.ok);
    assert_eq!(rt.status, "failed");
    assert!(rt.reason.as_deref().unwrap().contains("运行异常"));
    assert!(rt.suggestion.as_deref().unwrap().contains("系统恢复"));
}

#[test]
fn health_detail_core_down_reason_suggestion() {
    let hd = runtime::health_detail(&status_with("ready", false, true));
    assert!(!hd.overall);
    let core = &hd.components[1];
    assert_eq!(core.name, "Core");
    assert!(!core.ok);
    assert_eq!(core.status, "down");
    assert_eq!(core.reason.as_deref(), Some("核心服务未运行"));
    assert!(core.suggestion.is_some());
}

#[test]
fn health_detail_console_down() {
    let hd = runtime::health_detail(&status_with("ready", true, false));
    assert!(!hd.overall);
    let console = &hd.components[2];
    assert_eq!(console.name, "Console");
    assert!(!console.ok);
    assert_eq!(console.status, "down");
}

#[test]
fn health_detail_starting() {
    let hd = runtime::health_detail(&status_with("starting", false, false));
    assert!(!hd.overall);
    let rt = &hd.components[0];
    assert!(!rt.ok);
    assert_eq!(rt.status, "starting");
    assert_eq!(rt.reason.as_deref(), Some("工厂正在初始化"));
}

#[test]
fn health_detail_stopped_suggestion() {
    let hd = runtime::health_detail(&status_with("stopped", false, false));
    assert!(!hd.overall);
    let rt = &hd.components[0];
    assert_eq!(rt.status, "stopped");
    assert!(rt.suggestion.is_some());
}

#[test]
fn health_detail_component_order_names() {
    let hd = runtime::health_detail(&status_with("ready", true, true));
    let names: Vec<&str> = hd.components.iter().map(|c| c.name).collect();
    assert_eq!(names, vec!["Runtime", "Core", "Console"]);
}

// ================================================================ 15A-3b
// uptime / ISO8601 解析
// ================================================================

#[test]
fn parse_iso8601_valid() {
    let t = runtime::parse_iso8601_secs("2026-08-07T00:00:00Z").unwrap();
    assert_eq!(t % 86400, 0, "整点 UTC 秒");
    let t2 = runtime::parse_iso8601_secs("2026-08-07T01:02:03.123Z").unwrap();
    assert_eq!(t2 - t, 3600 + 120 + 3, "小数秒截断");
}

#[test]
fn parse_iso8601_malformed_rejected() {
    for bad in [
        "",
        "not-a-date",
        "2026-13-01T00:00:00Z", // 月越界
        "2026-08-07",           // 无时间
        "2026-08-07T25:00:00Z", // 时越界
        "2026-08-07T00:00",     // 无秒
    ] {
        assert!(
            runtime::parse_iso8601_secs(bad).is_none(),
            "应拒绝非法时间戳: {bad}"
        );
    }
}

#[test]
fn uptime_secs_at_computes() {
    let base = runtime::parse_iso8601_secs("2026-08-07T00:00:00Z").unwrap();
    assert_eq!(
        runtime::uptime_secs_at(Some("2026-08-07T00:00:00Z"), base + 125),
        Some(125)
    );
    assert_eq!(
        runtime::uptime_secs_at(None, base),
        None,
        "无 started_at → None"
    );
    assert_eq!(
        runtime::uptime_secs_at(Some("2026-08-07T00:00:00Z"), base - 10),
        Some(0),
        "未来时间 → 0"
    );
}

// ================================================================ 15A-3b
// friendly_error — 用户语言, 无技术细节
// ================================================================

/// 用户语言断言: 禁暴露 Python/Rust/uvicorn/subprocess/exit code 等。
fn assert_no_tech_terms(s: &str) {
    for t in [
        "python",
        "Python",
        "rust",
        "Rust",
        "uvicorn",
        "subprocess",
        "pip ",
        "stdout",
        "stderr",
        "exit=",
        "spawn",
        ".py",
        "exit code",
        "traceback",
    ] {
        assert!(!s.contains(t), "用户语言禁含技术细节 '{t}': {s}");
    }
}

#[test]
fn friendly_error_all_start_with_factory_startup_failed() {
    let cases = [
        BridgeError::SpawnFailed("x".into()),
        BridgeError::Exit {
            code: 1,
            stdout: "".into(),
            stderr: "".into(),
        },
        BridgeError::Timeout(Duration::from_secs(1)),
        BridgeError::Parse("bad".into()),
        BridgeError::DataRoot("bad".into()),
        BridgeError::Health("bad".into()),
        BridgeError::RuntimeFailed("bad".into()),
    ];
    for e in cases {
        let m = friendly_error(&e);
        assert!(m.starts_with("Factory startup failed"), "got: {m}");
        assert_no_tech_terms(&m);
    }
}

#[test]
fn friendly_error_spawn_mentions_install() {
    let m = friendly_error(&BridgeError::SpawnFailed("no such file".into()));
    assert_no_tech_terms(&m);
    assert!(m.contains("未安装") || m.contains("无法启动"), "got: {m}");
}

#[test]
fn friendly_error_exit_strips_command_output() {
    let e = BridgeError::Exit {
        code: 1,
        stdout: "boom stdout".into(),
        stderr: "Traceback (most recent call last)".into(),
    };
    let m = friendly_error(&e);
    assert_no_tech_terms(&m);
    assert!(!m.contains("boom"), "禁透传 stdout: {m}");
    assert!(!m.contains("Traceback"), "禁透传 stderr: {m}");
}

#[test]
fn friendly_error_dataroot_user_language() {
    let m = friendly_error(&BridgeError::DataRoot("unwritable".into()));
    assert_no_tech_terms(&m);
    assert!(m.contains("数据目录"), "got: {m}");
}

#[test]
fn friendly_error_health_user_language() {
    let m = friendly_error(&BridgeError::Health("unreachable".into()));
    assert_no_tech_terms(&m);
    assert!(m.contains("控制台") || m.contains("未就绪"), "got: {m}");
}

#[test]
fn friendly_error_runtime_failed_suggests_recovery() {
    let m = friendly_error(&BridgeError::RuntimeFailed("crash".into()));
    assert_no_tech_terms(&m);
    assert!(m.contains("系统恢复"), "got: {m}");
}

// ================================================================ 15A-3b
// status_label — UI 状态徽章文案
// ================================================================

#[test]
fn status_label_known_statuses() {
    assert_eq!(status_label("ready"), "READY");
    assert_eq!(status_label("starting"), "STARTING");
    assert_eq!(status_label("stopping"), "STOPPING");
    assert_eq!(status_label("stopped"), "STOPPED");
    assert_eq!(status_label("failed"), "FAILED");
    assert_eq!(status_label("idle"), "IDLE");
}

#[test]
fn status_label_unknown_uppercase_failsafe() {
    assert_eq!(status_label("weird"), "WEIRD");
}

// ================================================================ 15A-3b
// launcher UI 资源静态断言 (内嵌 Tauri 资源, 原生 JS)
// ================================================================

/// launcher UI 目录 (crate 编译时路径 = desktop/src-tauri)。
fn ui_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../src/ui")
}

fn ui_file(name: &str) -> String {
    fs::read_to_string(ui_dir().join(name))
        .unwrap_or_else(|e| panic!("读取 launcher 资源 {name} 失败: {e}"))
}

#[test]
fn launcher_html_has_factory_header() {
    let html = ui_file("launcher.html");
    assert!(
        html.contains("AI Organization Factory"),
        "Factory Header 品牌名"
    );
    assert!(html.contains("factory-header"));
    assert!(html.contains("构建 · 运行 · 管理你的 AI 企业组织"));
}

#[test]
fn launcher_html_has_workspace_placeholder() {
    let html = ui_file("launcher.html");
    assert!(html.contains("Workspace 即将上线"), "Workspace 预留占位");
    assert!(html.contains("workspace-panel"));
    assert!(html.contains("CEO"), "预留 CEO 模块");
    assert!(html.contains("Approval"), "预留 Approval 模块");
}

#[test]
fn launcher_html_has_system_status_panel() {
    let html = ui_file("launcher.html");
    assert!(html.contains("System Status"));
    assert!(html.contains("status-badge"));
    assert!(html.contains("st-uptime"));
    assert!(html.contains("st-port"));
    assert!(html.contains("st-version"));
}

#[test]
fn launcher_html_has_three_log_tabs() {
    let html = ui_file("launcher.html");
    for tab in ["runtime.log", "core.log", "console.log"] {
        assert!(html.contains(tab), "日志 tab 缺失: {tab}");
    }
    assert!(html.contains("Logs"), "Log Viewer 定位 (Troubleshooting)");
}

#[test]
fn launcher_html_has_recovery_section() {
    let html = ui_file("launcher.html");
    assert!(html.contains("System Recovery"));
    assert!(html.contains("Restart Runtime"));
    assert!(html.contains("recovery-panel"));
}

#[test]
fn launcher_js_poll_interval_two_seconds() {
    let js = ui_file("launcher.js");
    assert!(js.contains("STATUS_POLL_MS = 2000"), "状态轮询应为 2s");
    assert!(js.contains("setInterval(pollTick, STATUS_POLL_MS)"));
}

#[test]
fn launcher_js_invokes_required_commands() {
    let js = ui_file("launcher.js");
    for cmd in [
        "runtime_status",
        "runtime_logs",
        "runtime_restart",
        "health_detail",
        "open_console",
        "runtime_start",
    ] {
        assert!(
            js.contains(&format!("\"{cmd}\"")),
            "launcher.js 应调用 {cmd}"
        );
    }
}

#[test]
fn launcher_js_no_business_command() {
    let js = ui_file("launcher.js");
    for cmd in [
        "create_agent",
        "create_project",
        "assign_task",
        "create_company",
        "save_knowledge",
        "create_org",
    ] {
        assert!(!js.contains(cmd), "launcher.js 禁 business command: {cmd}");
    }
}

#[test]
fn launcher_ui_no_tech_terms() {
    let html = ui_file("launcher.html");
    let js = ui_file("launcher.js");
    for t in ["uvicorn", "subprocess", "python", "pip install"] {
        assert!(!html.contains(t), "launcher.html 禁技术细节: {t}");
        assert!(!js.contains(t), "launcher.js 禁技术细节: {t}");
    }
}

#[test]
fn launcher_css_embedded_and_referenced() {
    let html = ui_file("launcher.html");
    assert!(html.contains("launcher.css"), "html 应引用 launcher.css");
    let css = ui_file("launcher.css");
    assert!(css.contains("factory-header"));
    assert!(css.contains("--bg"));
    assert!(css.contains(".tab"), "日志 tab 样式");
}

#[test]
fn ui_status_label_js_rust_alignment() {
    // launcher.js statusLabel 映射必须与 Rust status_label 一致
    let js = ui_file("launcher.js");
    for st in ["ready", "starting", "stopping", "stopped", "failed", "idle"] {
        let pat = format!("case \"{st}\": return \"{}\"", status_label(st));
        assert!(js.contains(&pat), "launcher.js statusLabel({st}) 缺: {pat}");
    }
}

// ================================================================ 15A-3b
// 产品级流程 (Fresh Launch / Failure Recovery / Shutdown)
// ================================================================

#[test]
fn product_fresh_launch_ready_console() {
    // Fresh Launch: launch → ready → health 全绿 → console 可导航 → shutdown
    let dir = TestDir::new("prod_fresh");
    let port = free_port();
    let b = bridge_for(&dir, &[("FAKE_RUNTIME_PORT", &port.to_string())]);
    let launched = launch_flow(&b, dir.path(), Duration::from_secs(5)).unwrap();
    assert_eq!(launched.status.status, "ready");
    let hd = runtime::health_detail(&launched.status);
    assert!(hd.overall, "Fresh Launch: 三组件应全绿");
    assert_eq!(hd.port, Some(port));
    // console URL (open_console 导航目标) 可达
    assert!(runtime::http_health(port, Duration::from_secs(2)));
    let st = shutdown_flow(&b, dir.path()).unwrap();
    assert_eq!(st.status, "stopped");
    cleanup_children(dir.path());
}

#[test]
fn product_failure_recovery_restart() {
    // Failure Recovery: start 失败 → 用户语言错误 → restart → 恢复 ready
    let dir = TestDir::new("prod_recover");
    let port = free_port();
    let b_fail = bridge_for(&dir, &[("FAKE_RUNTIME_FAIL", "exit")]);
    let e = b_fail.runtime_start(dir.path()).unwrap_err();
    let msg = friendly_error(&e);
    assert!(msg.starts_with("Factory startup failed"));
    assert_no_tech_terms(&msg);
    let b = bridge_for(&dir, &[("FAKE_RUNTIME_PORT", &port.to_string())]);
    let st = b.runtime_restart(dir.path()).unwrap();
    assert_eq!(st.status, "ready");
    assert_eq!(st.port, Some(port));
    let hd = runtime::health_detail(&st);
    assert!(hd.overall, "恢复后健康应全绿");
    shutdown_flow(&b, dir.path()).unwrap();
    cleanup_children(dir.path());
}

#[test]
fn product_shutdown_graceful_after_launch() {
    // Shutdown: launch → close (graceful stop) → 无残留 + health 显示 stopped
    let dir = TestDir::new("prod_shutdown");
    let port = free_port();
    let b = bridge_for(&dir, &[("FAKE_RUNTIME_PORT", &port.to_string())]);
    let launched = launch_flow(&b, dir.path(), Duration::from_secs(5)).unwrap();
    let root = dir.path();
    let console_pid: i32 = fs::read_to_string(root.join("config/console.pid"))
        .unwrap()
        .trim()
        .parse()
        .unwrap();
    let st = shutdown_flow(&b, root).unwrap();
    assert_eq!(st.status, "stopped");
    let hd = runtime::health_detail(&st);
    assert!(!hd.overall, "关闭后 health 不应 overall");
    let rt = &hd.components[0];
    assert_eq!(rt.status, "stopped");
    assert!(!rt.ok);
    assert!(rt.suggestion.is_some(), "stopped 应有用户语言建议");
    let deadline = std::time::Instant::now() + Duration::from_secs(3);
    while pid_alive(console_pid) && std::time::Instant::now() < deadline {
        std::thread::sleep(Duration::from_millis(50));
    }
    assert!(!pid_alive(console_pid), "graceful shutdown: 无残留进程");
    assert!(!root.join("config/console.pid").exists());
    assert!(!root.join("config/core.pid").exists());
}

#[test]
fn product_restart_after_crash_recovers() {
    // runtime 启动即崩溃 (crash_after_start) → restart 恢复 → ready + health 绿
    let dir = TestDir::new("prod_crash");
    let b_crash = bridge_for(&dir, &[("FAKE_RUNTIME_FAIL", "crash_after_start")]);
    let e = b_crash.runtime_start(dir.path()).unwrap_err();
    assert!(
        matches!(e, BridgeError::Exit { code: 1, .. }),
        "前置: 启动应崩溃"
    );
    let b = bridge_for(&dir, &[]);
    let st = b.runtime_restart(dir.path()).unwrap();
    assert_eq!(st.status, "ready");
    assert!(runtime::health_detail(&st).overall, "崩溃恢复后健康应全绿");
    shutdown_flow(&b, dir.path()).unwrap();
    cleanup_children(dir.path());
}

#[test]
fn product_error_user_language_end_to_end() {
    // 全链路: fake CLI 输出技术错误 (stderr traceback) → friendly_error 只含用户语言
    let dir = TestDir::new("prod_lang");
    let b = bridge_for(&dir, &[("FAKE_RUNTIME_FAIL", "exit")]);
    let e = b.runtime_start(dir.path()).unwrap_err();
    let raw = e.to_string();
    assert!(
        raw.contains("exit=1") || raw.contains("fake runtime exit failure"),
        "底层错误仍保留技术信息 (bridge 层)"
    );
    let msg = friendly_error(&e);
    assert_no_tech_terms(&msg);
    assert!(msg.contains("Factory startup failed"));
    // error_html (兜底页) 也不含技术词
    let html = error_html(&msg);
    assert!(!html.contains("pip install"));
    assert!(!html.contains("python"));
    assert!(html.contains("启动失败"));
}

// ================================================================ 15A-3c-3
// macOS dmg 打包契约 (App 结构 / embedded discovery / dmg smoke / first launch)
// dist/ 与 target/release 产物 gitignored — 未构建时 guard-skip (等价 @skipif)。
// ================================================================

/// dist/factory-runtime-bundle 目录 (tauri.conf bundle.resources 指向; 未构建 → None)。
fn dist_bundle_dir() -> Option<PathBuf> {
    let p = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../dist/factory-runtime-bundle");
    if p.join("factory-runtime-bundle").is_file() {
        Some(p)
    } else {
        None
    }
}

/// dmg 产物路径 (Tauri 命名: <productName>_<version>_<arch>.dmg; 未构建 → None)。
/// target/ 位于 CARGO_MANIFEST_DIR (src-tauri/) 之下, 无上级跳转。
fn dmg_bundle_path() -> Option<PathBuf> {
    let dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("target/release/bundle/dmg");
    let entries = fs::read_dir(&dir).ok()?;
    let dmg = entries.filter_map(|e| e.ok()).find(|e| {
        let n = e.file_name();
        let n = n.to_string_lossy();
        n.starts_with("AI Organization Factory") && n.ends_with(".dmg")
    })?;
    let p = dmg.path();
    if p.is_file() {
        Some(p)
    } else {
        None
    }
}

#[test]
fn bundle_resource_contract_dist_bundle_exists() {
    // App 结构契约: bundle.resources → dist/factory-runtime-bundle/
    // (PyInstaller onedir: 主二进制 + _internal/ 内嵌解释器目录)
    let Some(dir) = dist_bundle_dir() else {
        eprintln!("SKIP: dist/factory-runtime-bundle 未构建 (dist/ gitignored)");
        return;
    };
    assert!(
        dir.join("factory-runtime-bundle").is_file(),
        "bundle 主二进制缺失: {}",
        dir.display()
    );
    assert!(
        dir.join("_internal").is_dir(),
        "PyInstaller onedir _internal 目录缺失"
    );
}

#[test]
fn bundle_embedded_interpreter_independent_of_system_python() {
    // macOS onedir 契约: _internal/ 内嵌解释器 (Python.framework / python3.12 / Python)
    // — App 运行时不需要系统 python (fresh machine 无 python 依赖)
    let Some(dir) = dist_bundle_dir() else {
        eprintln!("SKIP: dist/factory-runtime-bundle 未构建");
        return;
    };
    let internal = dir.join("_internal");
    let embedded = internal.join("Python.framework").exists()
        || internal.join("python3.12").exists()
        || internal.join("Python").exists();
    assert!(
        embedded,
        "内嵌解释器缺失 (Python.framework / python3.12 / Python): {}",
        internal.display()
    );
}

#[test]
fn bundle_discovery_resolves_real_dist_bundle() {
    // 集成: discovery (embedded > PATH) 对真实 dist bundle 生效 — resolve 出
    // dist/factory-runtime-bundle/factory-runtime-bundle 绝对路径 (App 内嵌形态)
    let Some(dir) = dist_bundle_dir() else {
        eprintln!("SKIP: dist/factory-runtime-bundle 未构建");
        return;
    };
    let resource_dir = dir.parent().unwrap(); // 打包后 resource_dir = dist/ 同级
    let cmd = embedded_runtime_cmd(resource_dir).expect("embedded 探测应命中 dist bundle");
    assert!(
        cmd.ends_with("factory-runtime-bundle/factory-runtime-bundle"),
        "got: {cmd}"
    );
    let _g = ENV_LOCK.lock().unwrap();
    remove_env("DESKTOP_RUNTIME_CMD");
    assert_eq!(
        resolve_runtime_cmd_at(Some(resource_dir)),
        cmd,
        "embedded 应优先于 PATH (真实 bundle)"
    );
}

#[test]
fn missing_runtime_full_chain_friendly() {
    // 无 env + 无 embedded (空 resource_dir) → PATH 回退 → spawn 失败 →
    // launch_flow 报错 → friendly_error 全用户语言 (fresh machine 无 runtime 场景)
    let _g = ENV_LOCK.lock().unwrap();
    remove_env("DESKTOP_RUNTIME_CMD");
    let dir = TestDir::new("pkg_missing");
    let cmd = resolve_runtime_cmd_at(Some(dir.path()));
    assert_eq!(
        cmd,
        runtime::DEFAULT_RUNTIME_CMD,
        "空 resource_dir → PATH 回退"
    );
    let b = Bridge::new(cmd);
    let e = launch_flow(&b, dir.path(), Duration::from_secs(5)).unwrap_err();
    assert!(matches!(e, BridgeError::SpawnFailed(_)), "got {e:?}");
    let msg = friendly_error(&e);
    assert!(msg.starts_with("Factory startup failed"), "got: {msg}");
    assert_no_tech_terms(&msg);
}

#[test]
fn dmg_smoke_metadata() {
    // dmg smoke (@skipif 未构建): dmg 是发布产物 — 存在 + 大小;
    // .app 是中间产物 (bundle_dmg.sh 打包后清理, macos/ 目录可为空),
    // 仅当残留时验证结构契约 (Contents/MacOS 主二进制 +
    // Resources/factory-runtime-bundle 内嵌 onedir)
    let Some(dmg) = dmg_bundle_path() else {
        eprintln!("SKIP: dmg 未构建 (tauri build --bundles dmg 后重跑)");
        return;
    };
    let meta = fs::metadata(&dmg).unwrap();
    assert!(
        meta.len() > 5 * 1024 * 1024,
        "dmg 过小 ({} bytes, 应含 38M 内嵌 runtime)",
        meta.len()
    );
    let app = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("target/release/bundle/macos/AI Organization Factory.app");
    if !app.is_dir() {
        // 构建清理语义: .app 中间产物可被构建流程删除, dmg 才是发布产物
        return;
    }
    assert!(
        app.join("Contents/MacOS/AI Organization Factory").is_file(),
        "主二进制缺失"
    );
    let res = app.join("Contents/Resources/factory-runtime-bundle");
    assert!(
        res.join("factory-runtime-bundle").is_file(),
        "Resources/factory-runtime-bundle 内嵌缺失 (bundle.resources 契约)"
    );
    assert!(
        res.join("_internal").is_dir(),
        "内嵌 _internal (PyInstaller onedir) 缺失"
    );
}

#[test]
fn first_launch_creates_state_and_three_logs() {
    // First Launch (fake runtime): data_root 初始化 → ready →
    // 三日志文件 (runtime/core/console.log) 落盘 → graceful stop 写入 runtime.log
    let dir = TestDir::new("pkg_first");
    let port = free_port();
    let b = bridge_for(&dir, &[("FAKE_RUNTIME_PORT", &port.to_string())]);
    let launched = launch_flow(&b, dir.path(), Duration::from_secs(5)).unwrap();
    assert_eq!(launched.status.status, "ready");
    let root = dir.path();
    assert!(
        root.join("config/runtime_state.json").is_file(),
        "首次启动应写状态文件"
    );
    for name in ["runtime.log", "core.log", "console.log"] {
        let log = root.join("logs").join(name);
        assert!(log.is_file(), "日志缺失: {name}");
        let text = fs::read_to_string(&log).unwrap();
        assert!(!text.trim().is_empty(), "日志为空: {name}");
    }
    let st = shutdown_flow(&b, root).unwrap();
    assert_eq!(st.status, "stopped");
    let rt_log = fs::read_to_string(root.join("logs/runtime.log")).unwrap();
    assert!(
        rt_log.contains("stopped"),
        "graceful stop 应写入 runtime.log"
    );
    cleanup_children(root);
}
