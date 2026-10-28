import os
from pathlib import Path
import shutil
import sys
import threading


def main():
    # Frozen MCP subprocess reuses this executable with an explicit mode switch.
    if '--mcp-server' in sys.argv:
        from examples.mcp_server import main as mcp_main
        mcp_main()
        return
    import webview
    from server.app import State, make_server
    resources = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
    data = Path(os.environ.get('LITTLE_CURSOR_DATA', str(Path.home() / 'Library/Application Support/LittleCursor')))
    workspace = data / 'workspace'
    if not workspace.exists():
        shutil.copytree(resources / 'examples/demo_workspace', workspace)
    state = State(resources, workspace, data)
    server = make_server(state)
    class Bridge:
        def choose_workspace(self):
            if any(not j['done'] for j in state.jobs.values()):
                return {'error': '请先结束任务'}
            result = window.create_file_dialog(webview.FOLDER_DIALOG)
            if result:
                state.workspace = Path(result[0]).resolve()
                state.history = []
            return {'workspace': str(state.workspace)}
    threading.Thread(target=server.serve_forever, daemon=True).start()
    window = webview.create_window('Little Cursor · 我的编程智能体', f'http://127.0.0.1:{server.server_port}/?token={state.token}',
                                  js_api=Bridge(), width=1440, height=920, min_size=(1080, 700), background_color='#111318')
    try:
        webview.start(debug=False)
    finally:
        for job in state.jobs.values():
            job['cancel'].set()
        server.shutdown()


if __name__ == '__main__':
    main()
