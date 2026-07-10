import type {
  PythonBridgeObject,
  RpcResult,
  SimulationState,
  SimulationStatus,
} from './types.js';

type BridgeMethod = Exclude<keyof PythonBridgeObject, keyof EventBridge>;

interface EventBridge {
  simulationStateChanged: unknown;
  simulationStatusChanged: unknown;
  consoleMessage: unknown;
}

export class EditorBridgeClient {
  constructor(private readonly bridge: PythonBridgeObject | null) {}

  static connect(): Promise<EditorBridgeClient> {
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

  get available(): boolean {
    return this.bridge !== null;
  }

  call<T>(method: BridgeMethod, ...args: unknown[]): Promise<RpcResult<T>> {
    return new Promise((resolve) => {
      if (!this.bridge) {
        resolve({ ok: false, error: `Python bridge unavailable: ${String(method)}` });
        return;
      }
      const callable = this.bridge[method] as unknown as (...values: unknown[]) => void;
      callable(...args, (result: string) => {
        try {
          resolve(JSON.parse(result) as RpcResult<T>);
        } catch (error) {
          resolve({ ok: false, error: `Invalid bridge response: ${String(error)}` });
        }
      });
    });
  }

  syncEditorState(sceneJson: string, dirty: boolean, currentPath: string | null): void {
    this.bridge?.setEditorState(sceneJson, dirty, currentPath ?? '');
  }

  onSimulationState(callback: (state: SimulationState) => void): void {
    this.bridge?.simulationStateChanged.connect((stateJson) => {
      callback(JSON.parse(stateJson) as SimulationState);
    });
  }

  onSimulationStatus(callback: (status: SimulationStatus) => void): void {
    this.bridge?.simulationStatusChanged.connect((status) => {
      callback(status as SimulationStatus);
    });
  }

  onConsoleMessage(callback: (message: string) => void): void {
    this.bridge?.consoleMessage.connect(callback);
  }
}
