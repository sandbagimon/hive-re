import type { RpcResult, SimulationState, SimulationStatus } from './types.js';

type BridgeMethod =
  | 'getAssets' | 'importOpenUsd' | 'importOpenUsdFolder'
  | 'getVisualGeometry' | 'getVisualGeometryBundle'
  | 'getLocalSceneManifest' | 'getLocalSceneChunk'
  | 'openProject' | 'saveProject'
  | 'validateProjectContent' | 'exportMjcf' | 'preflight'
  | 'runSimulation' | 'pauseSimulation' | 'setSimulationSpeed'
  | 'stepSimulation' | 'resetSimulation' | 'discardSimulation'
  | 'setJointTargets' | 'setActuatorControls' | 'setAttachmentCommands'
  | 'loadController' | 'reloadController' | 'detachController'
  | 'loadTrajectory' | 'playTrajectory' | 'pauseTrajectory' | 'stopTrajectory'
  | 'startRecording' | 'stopRecording' | 'getRecording'
  | 'exportRecordingDialog';

interface RuntimeConfig {
  apiBaseUrl: string;
  webSocketBaseUrl: string;
  apiVersion: 'v1';
  projectId: string | null;
  accessToken: string | null;
}

interface ArtifactPayload {
  id: string;
  filename: string;
  media_type: string;
  download_url: string;
}

interface ApiEvent {
  version: 'v1';
  simulation_id: string;
  sequence: number;
  type: 'snapshot' | 'state' | 'status' | 'console' | 'title' | 'heartbeat';
  payload: unknown;
}

class ApiRequestError extends Error {
  constructor(message: string, readonly data?: unknown) {
    super(message);
  }
}

export class EditorBridgeClient {
  private readonly stateCallbacks: Array<(state: SimulationState) => void> = [];
  private readonly statusCallbacks: Array<(status: SimulationStatus) => void> = [];
  private readonly consoleCallbacks: Array<(message: string) => void> = [];
  private projectId: string | null = null;
  private simulationId: string | null = null;
  private simulationSceneJson: string | null = null;
  private lastSequence = 0;
  private lastState: SimulationState | null = null;
  private lastStatus: SimulationStatus = 'stopped';
  private socket: WebSocket | null = null;
  private reconnectTimer: number | null = null;
  private reconnectDelay = 250;
  private sceneSync: Promise<void> = Promise.resolve();
  private lastSceneJson = '';
  private controllerUpload: { filename: string; source: string } | null = null;
  private projectInitialization: Promise<void> | null = null;

  constructor(
    private readonly config: RuntimeConfig | null = null,
    private connectionError: string | null = null,
  ) {}

  static async connect(): Promise<EditorBridgeClient> {
    try {
      const response = await fetch(new URL('simlab-config.json', document.baseURI), {
        cache: 'no-store',
      });
      if (!response.ok) throw new Error(`runtime config HTTP ${response.status}`);
      const raw = await response.json() as Partial<RuntimeConfig>;
      if (raw.apiVersion !== 'v1') throw new Error('runtime config must select API v1');
      const config: RuntimeConfig = {
        apiBaseUrl: EditorBridgeClient.normalizeHttpBase(raw.apiBaseUrl),
        webSocketBaseUrl: EditorBridgeClient.normalizeWebSocketBase(
          raw.webSocketBaseUrl,
          raw.apiBaseUrl,
        ),
        apiVersion: 'v1',
        projectId: raw.projectId ?? null,
        accessToken: raw.accessToken ?? null,
      };
      const client = new EditorBridgeClient(config);
      try {
        await client.ensureProject();
      } catch (error) {
        client.connectionError = error instanceof Error ? error.message : String(error);
      }
      return client;
    } catch (error) {
      return new EditorBridgeClient(null, error instanceof Error ? error.message : String(error));
    }
  }

  get available(): boolean {
    return this.config !== null && this.projectId !== null;
  }

  async call<T>(method: BridgeMethod, ...args: unknown[]): Promise<RpcResult<T>> {
    if (!this.config) return { ok: false, error: `Backend API unavailable: ${method}` };
    try {
      await this.ensureProject();
      return await this.dispatch<T>(method, args);
    } catch (error) {
      if (this.resetStaleResources(error)) {
        try {
          await this.ensureProject();
          return await this.dispatch<T>(method, args);
        } catch (retryError) {
          return this.failure<T>(retryError);
        }
      }
      return this.failure<T>(error);
    }
  }

  private failure<T>(error: unknown): RpcResult<T> {
      return {
        ok: false,
        error: error instanceof Error ? error.message : String(error),
        ...(error instanceof ApiRequestError && error.data !== undefined
          ? { data: error.data as T }
          : {}),
      };
  }

  syncEditorState(sceneJson: string, _dirty: boolean, _currentPath: string | null): void {
    if (!this.config || sceneJson === this.lastSceneJson) return;
    this.lastSceneJson = sceneJson;
    this.sceneSync = this.sceneSync
      .catch(() => undefined)
      .then(async () => {
        await this.ensureProject();
        await this.updateScene(sceneJson);
      })
      .catch((error: unknown) => {
        if (this.lastSceneJson === sceneJson) this.lastSceneJson = '';
        this.emitConsole(`Scene synchronization failed: ${String(error)}`);
      });
  }

  onSimulationState(callback: (state: SimulationState) => void): void {
    this.stateCallbacks.push(callback);
    if (this.lastState) callback(this.lastState);
  }

  onSimulationStatus(callback: (status: SimulationStatus) => void): void {
    this.statusCallbacks.push(callback);
    callback(this.lastStatus);
  }

  onConsoleMessage(callback: (message: string) => void): void {
    this.consoleCallbacks.push(callback);
    if (this.connectionError) callback(`Backend API unavailable: ${this.connectionError}`);
  }

  private async ensureProject(): Promise<void> {
    if (!this.config) throw new Error('Runtime configuration unavailable');
    if (this.projectId) return;
    if (!this.projectInitialization) {
      this.projectInitialization = (async () => {
        await this.request('/api/v1/health');
        if (this.config?.projectId) {
          await this.request(
            `/api/v1/projects/${encodeURIComponent(this.config.projectId)}`,
          );
          this.projectId = this.config.projectId;
        } else {
          const project = await this.request<{ id: string }>('/api/v1/projects', {
            method: 'POST',
            body: JSON.stringify({ name: 'Untitled Scene' }),
          });
          this.projectId = project.id;
        }
      })();
    }
    try {
      await this.projectInitialization;
      if (this.connectionError) this.emitConsole('Backend API connected.');
      this.connectionError = null;
    } catch (error) {
      this.connectionError = error instanceof Error ? error.message : String(error);
      throw error;
    } finally {
      this.projectInitialization = null;
    }
  }

  private resetStaleResources(error: unknown): boolean {
    if (!(error instanceof ApiRequestError)) return false;
    const unknownSimulation = error.message.startsWith('Unknown simulation:');
    const unknownProject = error.message.startsWith('Unknown project:');
    if (!unknownSimulation && (!unknownProject || this.config?.projectId)) return false;
    if (this.socket) this.socket.close();
    this.socket = null;
    if (this.reconnectTimer !== null) window.clearTimeout(this.reconnectTimer);
    this.reconnectTimer = null;
    this.simulationId = null;
    this.simulationSceneJson = null;
    this.lastSequence = 0;
    this.lastState = null;
    this.emitStatus('stopped');
    if (unknownProject) this.projectId = null;
    this.sceneSync = Promise.resolve();
    this.lastSceneJson = '';
    return true;
  }

  private async dispatch<T>(method: BridgeMethod, args: unknown[]): Promise<RpcResult<T>> {
    switch (method) {
      case 'getAssets': {
        const payload = await this.request<{ assets: unknown[]; local_scenes?: unknown[] }>(
          this.projectPath('/assets'),
        );
        return this.success<T>({
          assets: payload.assets,
          local_scenes: payload.local_scenes ?? [],
        });
      }
      case 'openProject':
        return this.openBrowserProject<T>();
      case 'saveProject':
        return this.saveBrowserProject<T>(String(args[0]));
      case 'validateProjectContent': {
        const project = await this.updateScene(String(args[0]));
        return this.success<T>({ scene: project.scene });
      }
      case 'importOpenUsd':
        return this.importOpenUsd<T>('file');
      case 'importOpenUsdFolder':
        return this.importOpenUsd<T>('folder');
      case 'getVisualGeometry':
        return this.getVisualGeometry<T>(String(args[0]));
      case 'getVisualGeometryBundle':
        return this.getVisualGeometryBundle<T>(String(args[0]));
      case 'getLocalSceneManifest':
        return this.getLocalSceneManifest<T>(String(args[0]));
      case 'getLocalSceneChunk':
        return this.getLocalSceneChunk<T>(String(args[0]), String(args[1]));
      case 'preflight':
        await this.synchronizeSceneArgument(args[0]);
        return this.success<T>(await this.request(this.projectPath('/preflight'), { method: 'POST' }));
      case 'exportMjcf':
        await this.synchronizeSceneArgument(args[0]);
        return this.exportMjcf<T>();
      case 'runSimulation':
        return this.simulationCommand<T>('/run', args[0]);
      case 'pauseSimulation':
        return this.simulationCommand<T>('/pause');
      case 'stepSimulation':
        return this.simulationCommand<T>('/step', args[0]);
      case 'resetSimulation':
        return this.simulationCommand<T>('/reset');
      case 'discardSimulation':
        await this.discardSimulation();
        return this.success<T>({});
      case 'setSimulationSpeed':
        return this.simulationRequest<T>('/speed', {
          method: 'PUT', body: JSON.stringify({ factor: Number(args[0]) }),
        });
      case 'setJointTargets':
        await this.synchronizeSceneArgument(args[0]);
        return this.simulationRequest<T>('/joint-targets', {
          method: 'PUT', body: JSON.stringify({ targets: JSON.parse(String(args[1])) }),
        });
      case 'setActuatorControls':
        await this.synchronizeSceneArgument(args[0]);
        return this.simulationRequest<T>('/actuator-controls', {
          method: 'PUT', body: JSON.stringify({ controls: JSON.parse(String(args[1])) }),
        });
      case 'setAttachmentCommands':
        await this.synchronizeSceneArgument(args[0]);
        return this.simulationRequest<T>('/attachments', {
          method: 'PUT', body: JSON.stringify({ commands: JSON.parse(String(args[1])) }),
        });
      case 'loadTrajectory':
        await this.synchronizeSceneArgument(args[0]);
        return this.simulationRequest<T>('/trajectory', {
          method: 'PUT', body: JSON.stringify({ trajectory: JSON.parse(String(args[1])) }),
        });
      case 'playTrajectory':
        return this.simulationCommand<T>('/trajectory/play');
      case 'pauseTrajectory':
        return this.simulationCommand<T>('/trajectory/pause');
      case 'stopTrajectory':
        return this.simulationCommand<T>('/trajectory/stop');
      case 'startRecording':
        await this.synchronizeSceneArgument(args[0]);
        return this.simulationRequest<T>('/recordings', {
          method: 'POST', body: String(args[1]),
        });
      case 'stopRecording':
        return this.simulationCommand<T>('/recordings/stop');
      case 'getRecording':
        return this.simulationRequest<T>('/recordings/current');
      case 'exportRecordingDialog':
        return this.exportRecording<T>(String(args[0]));
      case 'loadController':
        await this.synchronizeSceneArgument(args[0]);
        return this.loadController<T>();
      case 'reloadController':
        await this.synchronizeSceneArgument(args[0]);
        return this.reloadController<T>();
      case 'detachController':
        return this.simulationRequest<T>('/controller', { method: 'DELETE' });
    }
  }

  private async openBrowserProject<T>(): Promise<RpcResult<T>> {
    const file = (await this.chooseFiles('.json'))?.[0];
    if (!file) return { ok: false, error: 'Cancelled' };
    // The store may still be synchronizing the initial Untitled Scene. Serialize Open behind
    // that write so a late initial response can never overwrite the scene the user selected.
    await this.sceneSync;
    const project = await this.updateScene(await file.text());
    return this.success<T>({ scene: project.scene, path: file.name });
  }

  private async saveBrowserProject<T>(sceneJson: string): Promise<RpcResult<T>> {
    await this.sceneSync;
    const project = await this.updateScene(sceneJson);
    const scene = project.scene as { name?: string };
    const safeName = String(scene.name ?? 'scene')
      .replace(/[^a-z0-9_-]+/gi, '-')
      .replace(/^-|-$/g, '') || 'scene';
    const filename = `${safeName}.json`;
    this.download(filename, `${JSON.stringify(scene, null, 2)}\n`, 'application/json');
    return this.success<T>({ path: filename });
  }

  private async importOpenUsd<T>(mode: 'file' | 'folder'): Promise<RpcResult<T>> {
    const files = mode === 'folder'
      ? await this.chooseDirectory()
      : await this.chooseFiles('.usd,.usda,.usdc,.usdz,.zip');
    if (!files?.length) return { ok: false, error: 'Cancelled' };
    const entries = files.map((file) => ({
      file,
      name: (file.webkitRelativePath || file.name).replace(/\\/g, '/'),
    }));
    const entry = this.selectOpenUsdEntry(entries.map(({ name }) => name));
    if (entry === null) return { ok: false, error: 'Cancelled' };
    if (!entry) return { ok: false, error: 'No OpenUSD entry file selected' };
    const body = new FormData();
    body.set('entry', entry);
    for (const item of entries) body.append('files', item.file, item.name);
    const payload = await this.request(this.projectPath('/assets/openusd'), {
      method: 'POST', body,
    });
    return this.success<T>(payload);
  }

  private async getVisualGeometry<T>(artifactId: string): Promise<RpcResult<T>> {
    const payload = await this.request<Record<string, unknown>>(this.projectPath(
      `/geometry/${encodeURIComponent(artifactId)}`,
    ));
    const [baseColor, normal, roughness, metallic] = await Promise.all([
      this.textureArtifactUrl(payload.base_color_texture),
      this.textureArtifactUrl(payload.normal_texture),
      this.textureArtifactUrl(payload.roughness_texture),
      this.textureArtifactUrl(payload.metallic_texture),
    ]);
    if (baseColor) payload.base_color_texture_url = baseColor;
    if (normal) payload.normal_texture_url = normal;
    if (roughness) payload.roughness_texture_url = roughness;
    if (metallic) payload.metallic_texture_url = metallic;
    return this.success<T>(payload);
  }

  private async textureArtifactUrl(value: unknown): Promise<string | null> {
    if (typeof value !== 'string' || !value.startsWith('art_')) return null;
    const response = await this.requestResponse(
      `/api/v1/artifacts/${encodeURIComponent(value)}`,
    );
    return URL.createObjectURL(await response.blob());
  }

  private async getVisualGeometryBundle<T>(artifactId: string): Promise<RpcResult<T>> {
    const response = await this.requestResponse(
      `/api/v1/artifacts/${encodeURIComponent(artifactId)}`,
      { cache: 'force-cache' },
    );
    return this.success<T>(await response.arrayBuffer());
  }

  private async getLocalSceneManifest<T>(sceneId: string): Promise<RpcResult<T>> {
    const payload = await this.request(this.projectPath(
      `/local-scenes/${encodeURIComponent(sceneId)}/manifest`,
    ));
    return this.success<T>(payload);
  }

  private async getLocalSceneChunk<T>(sceneId: string, chunkId: string): Promise<RpcResult<T>> {
    const response = await this.requestResponse(this.projectPath(
      `/local-scenes/${encodeURIComponent(sceneId)}/chunks/${encodeURIComponent(chunkId)}`,
    ), { cache: 'force-cache' });
    return this.success<T>(await response.arrayBuffer());
  }

  private selectOpenUsdEntry(paths: string[]): string | null | undefined {
    const candidates = paths
      .filter((path) => /\.(usd|usda|usdc|usdz|zip)$/i.test(path))
      .sort((left, right) => {
        const depth = left.split('/').length - right.split('/').length;
        return depth || left.localeCompare(right);
      });
    if (candidates.length <= 1) return candidates[0];
    const shallowestDepth = candidates[0].split('/').length;
    const shallowest = candidates.filter((path) => path.split('/').length === shallowestDepth);
    if (shallowest.length === 1) return shallowest[0];
    const selected = window.prompt(
      `Select the OpenUSD entry file:\n${shallowest.join('\n')}`,
      shallowest[0],
    );
    if (selected === null) return null;
    const normalized = selected.replace(/\\/g, '/');
    if (!shallowest.includes(normalized)) {
      throw new Error(`Selected OpenUSD entry is not in the upload: ${normalized}`);
    }
    return normalized;
  }

  private async exportMjcf<T>(): Promise<RpcResult<T>> {
    const payload = await this.request<{ artifact: ArtifactPayload; issues: unknown[] }>(
      this.projectPath('/exports/mjcf'), { method: 'POST' },
    );
    await this.downloadArtifact(payload.artifact);
    return this.success<T>({ path: payload.artifact.filename, issues: payload.issues });
  }

  private async exportRecording<T>(formatName: string): Promise<RpcResult<T>> {
    if (formatName !== 'json' && formatName !== 'csv') {
      return { ok: false, error: `Unsupported recording format: ${formatName}` };
    }
    const payload = await this.simulationApi<{
      artifact: ArtifactPayload;
      sample_count: number;
      format: string;
    }>(`/recordings/${formatName}/artifact`, { method: 'POST' });
    await this.downloadArtifact(payload.artifact);
    return this.success<T>({
      path: payload.artifact.filename,
      format: payload.format,
      sample_count: payload.sample_count,
    });
  }

  private async loadController<T>(): Promise<RpcResult<T>> {
    const file = (await this.chooseFiles('.py'))?.[0];
    if (!file) return { ok: false, error: 'Cancelled' };
    this.controllerUpload = { filename: file.name, source: await file.text() };
    return this.sendController<T>(this.controllerUpload);
  }

  private async reloadController<T>(): Promise<RpcResult<T>> {
    if (!this.controllerUpload) return { ok: false, error: 'No uploaded controller to reload' };
    return this.sendController<T>(this.controllerUpload);
  }

  private async sendController<T>(upload: { filename: string; source: string }): Promise<RpcResult<T>> {
    return this.simulationRequest<T>('/controller', {
      method: 'POST',
      body: JSON.stringify(upload),
    });
  }

  private async simulationCommand<T>(path: string, sceneJson?: unknown): Promise<RpcResult<T>> {
    await this.synchronizeSceneArgument(sceneJson);
    return this.simulationRequest<T>(path, { method: 'POST' }, typeof sceneJson === 'string');
  }

  private async simulationRequest<T>(
    path: string,
    init: RequestInit = {},
    requireCurrentScene = false,
  ): Promise<RpcResult<T>> {
    return await this.simulationApi<RpcResult<T> & { version: string }>(
      path,
      init,
      requireCurrentScene,
    );
  }

  private async simulationApi<T>(
    path: string,
    init: RequestInit = {},
    requireCurrentScene = false,
  ): Promise<T> {
    const simulationId = await this.ensureSimulation(requireCurrentScene);
    return this.request<T>(`/api/v1/simulations/${encodeURIComponent(simulationId)}${path}`, init);
  }

  private async ensureSimulation(requireCurrentScene = false): Promise<string> {
    await this.sceneSync;
    if (
      this.simulationId
      && requireCurrentScene
      && this.simulationSceneJson !== this.lastSceneJson
    ) {
      await this.discardSimulation();
    }
    if (this.simulationId) return this.simulationId;
    const payload = await this.request<{
      id: string;
      snapshot: { sequence: number; status: SimulationStatus; state: SimulationState | null };
    }>('/api/v1/simulations', {
      method: 'POST', body: JSON.stringify({ project_id: this.requireProjectId() }),
    });
    this.simulationId = payload.id;
    this.simulationSceneJson = this.lastSceneJson;
    this.applySnapshot(payload.snapshot);
    this.connectWebSocket(payload.id);
    return payload.id;
  }

  private async discardSimulation(): Promise<void> {
    const simulationId = this.simulationId;
    if (!simulationId) return;
    const socket = this.socket;
    this.socket = null;
    socket?.close();
    if (this.reconnectTimer !== null) window.clearTimeout(this.reconnectTimer);
    this.reconnectTimer = null;
    this.simulationId = null;
    this.simulationSceneJson = null;
    this.lastSequence = 0;
    this.lastState = null;
    await this.request(`/api/v1/simulations/${encodeURIComponent(simulationId)}`, {
      method: 'DELETE',
    });
    this.emitStatus('stopped');
  }

  private async synchronizeSceneArgument(value: unknown): Promise<void> {
    if (typeof value === 'string' && value !== this.lastSceneJson) {
      this.syncEditorState(value, false, null);
    }
    await this.sceneSync;
  }

  private async updateScene(sceneJson: string): Promise<{ scene: unknown }> {
    const scene = JSON.parse(sceneJson) as Record<string, unknown>;
    const project = await this.request<{ scene: unknown }>(this.projectPath('/scene'), {
      method: 'PUT', body: JSON.stringify(scene),
    });
    this.lastSceneJson = JSON.stringify(project.scene);
    return project;
  }

  private connectWebSocket(simulationId: string): void {
    if (!this.config || simulationId !== this.simulationId) return;
    if (this.reconnectTimer !== null) window.clearTimeout(this.reconnectTimer);
    const params = new URLSearchParams({ after_sequence: String(this.lastSequence) });
    if (this.config.accessToken) params.set('token', this.config.accessToken);
    const socket = new WebSocket(
      `${this.config.webSocketBaseUrl}/api/v1/simulations/${encodeURIComponent(simulationId)}`
      + `/events?${params.toString()}`,
    );
    this.socket = socket;
    socket.addEventListener('open', () => { this.reconnectDelay = 250; });
    socket.addEventListener('message', (message) => {
      if (socket !== this.socket) return;
      const event = JSON.parse(String(message.data)) as ApiEvent;
      if (event.simulation_id !== this.simulationId) return;
      this.lastSequence = Math.max(this.lastSequence, event.sequence);
      if (event.type === 'snapshot') {
        this.applySnapshot(event.payload as {
          sequence: number; status: SimulationStatus; state: SimulationState | null;
        });
      } else if (event.type === 'state') {
        this.emitState(event.payload as SimulationState);
      } else if (event.type === 'status') {
        this.emitStatus(event.payload as SimulationStatus);
      } else if (event.type === 'console') {
        this.emitConsole(String(event.payload));
      } else if (event.type === 'title') {
        document.title = String(event.payload);
      }
    });
    socket.addEventListener('close', () => {
      if (socket !== this.socket || simulationId !== this.simulationId) return;
      this.reconnectTimer = window.setTimeout(
        () => this.connectWebSocket(simulationId),
        this.reconnectDelay,
      );
      this.reconnectDelay = Math.min(this.reconnectDelay * 2, 5000);
    });
  }

  private applySnapshot(snapshot: {
    sequence: number;
    status: SimulationStatus;
    state: SimulationState | null;
  }): void {
    this.lastSequence = Math.max(this.lastSequence, snapshot.sequence);
    this.emitStatus(snapshot.status);
    if (snapshot.state) this.emitState(snapshot.state);
  }

  private emitState(state: SimulationState): void {
    this.lastState = state;
    for (const callback of this.stateCallbacks) callback(state);
  }

  private emitStatus(status: SimulationStatus): void {
    this.lastStatus = status;
    for (const callback of this.statusCallbacks) callback(status);
  }

  private emitConsole(message: string): void {
    for (const callback of this.consoleCallbacks) callback(message);
  }

  private async request<T = unknown>(path: string, init: RequestInit = {}): Promise<T> {
    if (!this.config) throw new Error('Runtime configuration unavailable');
    const headers = new Headers(init.headers);
    if (init.body !== undefined && !(init.body instanceof FormData)) {
      headers.set('Content-Type', 'application/json');
    }
    if (this.config.accessToken) headers.set('Authorization', `Bearer ${this.config.accessToken}`);
    const response = await fetch(`${this.config.apiBaseUrl}${path}`, { ...init, headers });
    if (!response.ok) {
      let detail = `HTTP ${response.status}`;
      let errorData: unknown;
      try {
        const payload = await response.json() as {
          detail?: string;
          error?: string;
          data?: unknown;
        };
        detail = payload.detail ?? payload.error ?? detail;
        errorData = payload.data;
      } catch {
        // Keep the status-only fallback for non-JSON infrastructure errors.
      }
      throw new ApiRequestError(detail, errorData);
    }
    if (response.status === 204) return undefined as T;
    return await response.json() as T;
  }

  private projectPath(suffix: string): string {
    return `/api/v1/projects/${encodeURIComponent(this.requireProjectId())}${suffix}`;
  }

  private requireProjectId(): string {
    if (!this.projectId) throw new Error('Project resource unavailable');
    return this.projectId;
  }

  private success<T>(data: unknown): RpcResult<T> {
    return { ok: true, data: data as T };
  }

  private async downloadArtifact(artifact: ArtifactPayload): Promise<void> {
    const response = await this.requestResponse(artifact.download_url);
    this.download(artifact.filename, await response.blob(), artifact.media_type);
  }

  private async requestResponse(path: string, init: RequestInit = {}): Promise<Response> {
    if (!this.config) throw new Error('Runtime configuration unavailable');
    const headers = new Headers(init.headers);
    if (this.config.accessToken) headers.set('Authorization', `Bearer ${this.config.accessToken}`);
    const response = await fetch(`${this.config.apiBaseUrl}${path}`, { ...init, headers });
    if (!response.ok) throw new Error(`Artifact download HTTP ${response.status}`);
    return response;
  }

  private chooseFiles(accept: string, multiple = false): Promise<File[] | null> {
    return new Promise((resolve) => {
      const input = document.createElement('input');
      input.type = 'file';
      input.accept = accept;
      input.multiple = multiple;
      input.addEventListener('change', () => {
        resolve(input.files ? Array.from(input.files) : null);
      }, { once: true });
      input.click();
    });
  }

  private chooseDirectory(): Promise<File[] | null> {
    return new Promise((resolve) => {
      const input = document.createElement('input');
      input.type = 'file';
      input.multiple = true;
      input.setAttribute('webkitdirectory', '');
      input.addEventListener('change', () => {
        resolve(input.files ? Array.from(input.files) : null);
      }, { once: true });
      input.click();
    });
  }

  private download(filename: string, content: BlobPart, mediaType: string): void {
    const blob = content instanceof Blob ? content : new Blob([content], { type: mediaType });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(link.href), 0);
  }

  private static normalizeHttpBase(value: string | undefined): string {
    if (value === 'same-origin') return window.location.origin;
    const url = new URL(value ?? window.location.origin, window.location.href);
    if (url.protocol !== 'http:' && url.protocol !== 'https:') {
      throw new Error('apiBaseUrl must use HTTP or HTTPS');
    }
    return url.toString().replace(/\/$/, '');
  }

  private static normalizeWebSocketBase(value: string | undefined, httpValue: string | undefined): string {
    if (value === 'same-origin') {
      return `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}`;
    }
    const http = new URL(httpValue ?? window.location.origin, window.location.href);
    const fallback = `${http.protocol === 'https:' ? 'wss:' : 'ws:'}//${http.host}`;
    const url = new URL(value ?? fallback, window.location.href);
    if (url.protocol !== 'ws:' && url.protocol !== 'wss:') {
      throw new Error('webSocketBaseUrl must use WS or WSS');
    }
    return url.toString().replace(/\/$/, '');
  }
}
