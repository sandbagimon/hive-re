export class EditorBridgeClient {
    bridge;
    constructor(bridge) {
        this.bridge = bridge;
    }
    static connect() {
        return new Promise((resolve) => {
            if (!window.QWebChannel || !window.qt?.webChannelTransport) {
                resolve(new EditorBridgeClient(null));
                return;
            }
            new window.QWebChannel(window.qt.webChannelTransport, (channel) => {
                resolve(new EditorBridgeClient(channel.objects.simlabBridge));
            });
        });
    }
    get available() {
        return this.bridge !== null;
    }
    call(method, ...args) {
        return new Promise((resolve) => {
            if (!this.bridge) {
                resolve({ ok: false, error: `Python bridge unavailable: ${String(method)}` });
                return;
            }
            const callable = this.bridge[method];
            callable(...args, (result) => {
                try {
                    resolve(JSON.parse(result));
                }
                catch (error) {
                    resolve({ ok: false, error: `Invalid bridge response: ${String(error)}` });
                }
            });
        });
    }
    syncEditorState(sceneJson, dirty, currentPath) {
        this.bridge?.setEditorState(sceneJson, dirty, currentPath ?? '');
    }
    onSimulationState(callback) {
        this.bridge?.simulationStateChanged.connect((stateJson) => {
            callback(JSON.parse(stateJson));
        });
    }
    onSimulationStatus(callback) {
        this.bridge?.simulationStatusChanged.connect((status) => {
            callback(status);
        });
    }
    onConsoleMessage(callback) {
        this.bridge?.consoleMessage.connect(callback);
    }
}
