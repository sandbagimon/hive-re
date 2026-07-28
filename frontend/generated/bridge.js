class ApiRequestError extends Error {
    data;
    constructor(message, data) {
        super(message);
        this.data = data;
    }
}
export class EditorBridgeClient {
    config;
    connectionError;
    stateCallbacks = [];
    statusCallbacks = [];
    consoleCallbacks = [];
    projectId = null;
    simulationId = null;
    lastSequence = 0;
    lastState = null;
    lastStatus = 'stopped';
    socket = null;
    reconnectTimer = null;
    reconnectDelay = 250;
    sceneSync = Promise.resolve();
    lastSceneJson = '';
    controllerUpload = null;
    projectInitialization = null;
    constructor(config = null, connectionError = null) {
        this.config = config;
        this.connectionError = connectionError;
    }
    static async connect() {
        try {
            const response = await fetch(new URL('simlab-config.json', document.baseURI), {
                cache: 'no-store',
            });
            if (!response.ok)
                throw new Error(`runtime config HTTP ${response.status}`);
            const raw = await response.json();
            if (raw.apiVersion !== 'v1')
                throw new Error('runtime config must select API v1');
            const config = {
                apiBaseUrl: EditorBridgeClient.normalizeHttpBase(raw.apiBaseUrl),
                webSocketBaseUrl: EditorBridgeClient.normalizeWebSocketBase(raw.webSocketBaseUrl, raw.apiBaseUrl),
                apiVersion: 'v1',
                projectId: raw.projectId ?? null,
                accessToken: raw.accessToken ?? null,
            };
            const client = new EditorBridgeClient(config);
            try {
                await client.ensureProject();
            }
            catch (error) {
                client.connectionError = error instanceof Error ? error.message : String(error);
            }
            return client;
        }
        catch (error) {
            return new EditorBridgeClient(null, error instanceof Error ? error.message : String(error));
        }
    }
    get available() {
        return this.config !== null && this.projectId !== null;
    }
    async call(method, ...args) {
        if (!this.config)
            return { ok: false, error: `SimLab API unavailable: ${method}` };
        try {
            await this.ensureProject();
            return await this.dispatch(method, args);
        }
        catch (error) {
            if (this.resetStaleResources(error)) {
                try {
                    await this.ensureProject();
                    return await this.dispatch(method, args);
                }
                catch (retryError) {
                    return this.failure(retryError);
                }
            }
            return this.failure(error);
        }
    }
    failure(error) {
        return {
            ok: false,
            error: error instanceof Error ? error.message : String(error),
            ...(error instanceof ApiRequestError && error.data !== undefined
                ? { data: error.data }
                : {}),
        };
    }
    syncEditorState(sceneJson, _dirty, _currentPath) {
        if (!this.config || sceneJson === this.lastSceneJson)
            return;
        this.lastSceneJson = sceneJson;
        this.sceneSync = this.sceneSync
            .catch(() => undefined)
            .then(async () => {
            await this.ensureProject();
            await this.updateScene(sceneJson);
        })
            .catch((error) => {
            if (this.lastSceneJson === sceneJson)
                this.lastSceneJson = '';
            this.emitConsole(`Scene synchronization failed: ${String(error)}`);
        });
    }
    onSimulationState(callback) {
        this.stateCallbacks.push(callback);
        if (this.lastState)
            callback(this.lastState);
    }
    onSimulationStatus(callback) {
        this.statusCallbacks.push(callback);
        callback(this.lastStatus);
    }
    onConsoleMessage(callback) {
        this.consoleCallbacks.push(callback);
        if (this.connectionError)
            callback(`SimLab API unavailable: ${this.connectionError}`);
    }
    async ensureProject() {
        if (!this.config)
            throw new Error('Runtime configuration unavailable');
        if (this.projectId)
            return;
        if (!this.projectInitialization) {
            this.projectInitialization = (async () => {
                await this.request('/api/v1/health');
                if (this.config?.projectId) {
                    await this.request(`/api/v1/projects/${encodeURIComponent(this.config.projectId)}`);
                    this.projectId = this.config.projectId;
                }
                else {
                    const project = await this.request('/api/v1/projects', {
                        method: 'POST',
                        body: JSON.stringify({ name: 'Untitled Scene' }),
                    });
                    this.projectId = project.id;
                }
            })();
        }
        try {
            await this.projectInitialization;
            if (this.connectionError)
                this.emitConsole('SimLab API connected.');
            this.connectionError = null;
        }
        catch (error) {
            this.connectionError = error instanceof Error ? error.message : String(error);
            throw error;
        }
        finally {
            this.projectInitialization = null;
        }
    }
    resetStaleResources(error) {
        if (!(error instanceof ApiRequestError))
            return false;
        const unknownSimulation = error.message.startsWith('Unknown simulation:');
        const unknownProject = error.message.startsWith('Unknown project:');
        if (!unknownSimulation && (!unknownProject || this.config?.projectId))
            return false;
        if (this.socket)
            this.socket.close();
        this.socket = null;
        if (this.reconnectTimer !== null)
            window.clearTimeout(this.reconnectTimer);
        this.reconnectTimer = null;
        this.simulationId = null;
        this.lastSequence = 0;
        this.lastState = null;
        this.emitStatus('stopped');
        if (unknownProject)
            this.projectId = null;
        this.sceneSync = Promise.resolve();
        this.lastSceneJson = '';
        return true;
    }
    async dispatch(method, args) {
        switch (method) {
            case 'getAssets': {
                const payload = await this.request(this.projectPath('/assets'));
                return this.success({ assets: payload.assets });
            }
            case 'openProject':
                return this.openBrowserProject();
            case 'saveProject':
                return this.saveBrowserProject(String(args[0]));
            case 'validateProjectContent': {
                const project = await this.updateScene(String(args[0]));
                return this.success({ scene: project.scene });
            }
            case 'importOpenUsd':
                return this.importOpenUsd();
            case 'getVisualGeometry':
                return this.success(await this.request(this.projectPath(`/geometry/${encodeURIComponent(String(args[0]))}`)));
            case 'preflight':
                await this.synchronizeSceneArgument(args[0]);
                return this.success(await this.request(this.projectPath('/preflight'), { method: 'POST' }));
            case 'exportMjcf':
                await this.synchronizeSceneArgument(args[0]);
                return this.exportMjcf();
            case 'runSimulation':
                return this.simulationCommand('/run', args[0]);
            case 'pauseSimulation':
                return this.simulationCommand('/pause');
            case 'stepSimulation':
                return this.simulationCommand('/step', args[0]);
            case 'resetSimulation':
                return this.simulationCommand('/reset');
            case 'setSimulationSpeed':
                return this.simulationRequest('/speed', {
                    method: 'PUT', body: JSON.stringify({ factor: Number(args[0]) }),
                });
            case 'setJointTargets':
                await this.synchronizeSceneArgument(args[0]);
                return this.simulationRequest('/joint-targets', {
                    method: 'PUT', body: JSON.stringify({ targets: JSON.parse(String(args[1])) }),
                });
            case 'loadTrajectory':
                await this.synchronizeSceneArgument(args[0]);
                return this.simulationRequest('/trajectory', {
                    method: 'PUT', body: JSON.stringify({ trajectory: JSON.parse(String(args[1])) }),
                });
            case 'playTrajectory':
                return this.simulationCommand('/trajectory/play');
            case 'pauseTrajectory':
                return this.simulationCommand('/trajectory/pause');
            case 'stopTrajectory':
                return this.simulationCommand('/trajectory/stop');
            case 'startRecording':
                await this.synchronizeSceneArgument(args[0]);
                return this.simulationRequest('/recordings', {
                    method: 'POST', body: String(args[1]),
                });
            case 'stopRecording':
                return this.simulationCommand('/recordings/stop');
            case 'getRecording':
                return this.simulationRequest('/recordings/current');
            case 'exportRecordingDialog':
                return this.exportRecording(String(args[0]));
            case 'loadController':
                await this.synchronizeSceneArgument(args[0]);
                return this.loadController();
            case 'reloadController':
                await this.synchronizeSceneArgument(args[0]);
                return this.reloadController();
            case 'detachController':
                return this.simulationRequest('/controller', { method: 'DELETE' });
        }
    }
    async openBrowserProject() {
        const file = (await this.chooseFiles('.json'))?.[0];
        if (!file)
            return { ok: false, error: 'Cancelled' };
        const project = await this.updateScene(await file.text());
        return this.success({ scene: project.scene, path: file.name });
    }
    async saveBrowserProject(sceneJson) {
        const project = await this.updateScene(sceneJson);
        const scene = project.scene;
        const safeName = String(scene.name ?? 'scene')
            .replace(/[^a-z0-9_-]+/gi, '-')
            .replace(/^-|-$/g, '') || 'scene';
        const filename = `${safeName}.json`;
        this.download(filename, `${JSON.stringify(scene, null, 2)}\n`, 'application/json');
        return this.success({ path: filename });
    }
    async importOpenUsd() {
        const files = await this.chooseFiles('.usd,.usda,.usdc,.usdz', true);
        if (!files?.length)
            return { ok: false, error: 'Cancelled' };
        const entries = await Promise.all(files.map(async (file) => ({
            name: file.webkitRelativePath || file.name,
            content: await this.fileBase64(file),
        })));
        const entry = entries.find(({ name }) => /\.(usd|usda|usdc|usdz)$/i.test(name));
        if (!entry)
            return { ok: false, error: 'No OpenUSD entry file selected' };
        const payload = await this.request(this.projectPath('/assets/openusd'), {
            method: 'POST', body: JSON.stringify({ files: entries, entry: entry.name }),
        });
        return this.success(payload);
    }
    async exportMjcf() {
        const payload = await this.request(this.projectPath('/exports/mjcf'), { method: 'POST' });
        await this.downloadArtifact(payload.artifact);
        return this.success({ path: payload.artifact.filename, issues: payload.issues });
    }
    async exportRecording(formatName) {
        if (formatName !== 'json' && formatName !== 'csv') {
            return { ok: false, error: `Unsupported recording format: ${formatName}` };
        }
        const payload = await this.simulationApi(`/recordings/${formatName}/artifact`, { method: 'POST' });
        await this.downloadArtifact(payload.artifact);
        return this.success({
            path: payload.artifact.filename,
            format: payload.format,
            sample_count: payload.sample_count,
        });
    }
    async loadController() {
        const file = (await this.chooseFiles('.py'))?.[0];
        if (!file)
            return { ok: false, error: 'Cancelled' };
        this.controllerUpload = { filename: file.name, source: await file.text() };
        return this.sendController(this.controllerUpload);
    }
    async reloadController() {
        if (!this.controllerUpload)
            return { ok: false, error: 'No uploaded controller to reload' };
        return this.sendController(this.controllerUpload);
    }
    async sendController(upload) {
        return this.simulationRequest('/controller', {
            method: 'POST',
            body: JSON.stringify(upload),
        });
    }
    async simulationCommand(path, sceneJson) {
        await this.synchronizeSceneArgument(sceneJson);
        return this.simulationRequest(path, { method: 'POST' });
    }
    async simulationRequest(path, init = {}) {
        return await this.simulationApi(path, init);
    }
    async simulationApi(path, init = {}) {
        const simulationId = await this.ensureSimulation();
        return this.request(`/api/v1/simulations/${encodeURIComponent(simulationId)}${path}`, init);
    }
    async ensureSimulation() {
        await this.sceneSync;
        if (this.simulationId)
            return this.simulationId;
        const payload = await this.request('/api/v1/simulations', {
            method: 'POST', body: JSON.stringify({ project_id: this.requireProjectId() }),
        });
        this.simulationId = payload.id;
        this.applySnapshot(payload.snapshot);
        this.connectWebSocket(payload.id);
        return payload.id;
    }
    async synchronizeSceneArgument(value) {
        if (typeof value === 'string' && value !== this.lastSceneJson) {
            this.syncEditorState(value, false, null);
        }
        await this.sceneSync;
    }
    async updateScene(sceneJson) {
        const scene = JSON.parse(sceneJson);
        const project = await this.request(this.projectPath('/scene'), {
            method: 'PUT', body: JSON.stringify(scene),
        });
        this.lastSceneJson = JSON.stringify(project.scene);
        return project;
    }
    connectWebSocket(simulationId) {
        if (!this.config || simulationId !== this.simulationId)
            return;
        if (this.reconnectTimer !== null)
            window.clearTimeout(this.reconnectTimer);
        const params = new URLSearchParams({ after_sequence: String(this.lastSequence) });
        if (this.config.accessToken)
            params.set('token', this.config.accessToken);
        const socket = new WebSocket(`${this.config.webSocketBaseUrl}/api/v1/simulations/${encodeURIComponent(simulationId)}`
            + `/events?${params.toString()}`);
        this.socket = socket;
        socket.addEventListener('open', () => { this.reconnectDelay = 250; });
        socket.addEventListener('message', (message) => {
            if (socket !== this.socket)
                return;
            const event = JSON.parse(String(message.data));
            if (event.simulation_id !== this.simulationId)
                return;
            this.lastSequence = Math.max(this.lastSequence, event.sequence);
            if (event.type === 'snapshot') {
                this.applySnapshot(event.payload);
            }
            else if (event.type === 'state') {
                this.emitState(event.payload);
            }
            else if (event.type === 'status') {
                this.emitStatus(event.payload);
            }
            else if (event.type === 'console') {
                this.emitConsole(String(event.payload));
            }
            else if (event.type === 'title') {
                document.title = String(event.payload);
            }
        });
        socket.addEventListener('close', () => {
            if (socket !== this.socket || simulationId !== this.simulationId)
                return;
            this.reconnectTimer = window.setTimeout(() => this.connectWebSocket(simulationId), this.reconnectDelay);
            this.reconnectDelay = Math.min(this.reconnectDelay * 2, 5000);
        });
    }
    applySnapshot(snapshot) {
        this.lastSequence = Math.max(this.lastSequence, snapshot.sequence);
        this.emitStatus(snapshot.status);
        if (snapshot.state)
            this.emitState(snapshot.state);
    }
    emitState(state) {
        this.lastState = state;
        for (const callback of this.stateCallbacks)
            callback(state);
    }
    emitStatus(status) {
        this.lastStatus = status;
        for (const callback of this.statusCallbacks)
            callback(status);
    }
    emitConsole(message) {
        for (const callback of this.consoleCallbacks)
            callback(message);
    }
    async request(path, init = {}) {
        if (!this.config)
            throw new Error('Runtime configuration unavailable');
        const headers = new Headers(init.headers);
        if (init.body !== undefined)
            headers.set('Content-Type', 'application/json');
        if (this.config.accessToken)
            headers.set('Authorization', `Bearer ${this.config.accessToken}`);
        const response = await fetch(`${this.config.apiBaseUrl}${path}`, { ...init, headers });
        if (!response.ok) {
            let detail = `HTTP ${response.status}`;
            let errorData;
            try {
                const payload = await response.json();
                detail = payload.detail ?? payload.error ?? detail;
                errorData = payload.data;
            }
            catch {
                // Keep the status-only fallback for non-JSON infrastructure errors.
            }
            throw new ApiRequestError(detail, errorData);
        }
        if (response.status === 204)
            return undefined;
        return await response.json();
    }
    projectPath(suffix) {
        return `/api/v1/projects/${encodeURIComponent(this.requireProjectId())}${suffix}`;
    }
    requireProjectId() {
        if (!this.projectId)
            throw new Error('Project resource unavailable');
        return this.projectId;
    }
    success(data) {
        return { ok: true, data: data };
    }
    async downloadArtifact(artifact) {
        const response = await this.requestResponse(artifact.download_url);
        this.download(artifact.filename, await response.blob(), artifact.media_type);
    }
    async requestResponse(path) {
        if (!this.config)
            throw new Error('Runtime configuration unavailable');
        const headers = new Headers();
        if (this.config.accessToken)
            headers.set('Authorization', `Bearer ${this.config.accessToken}`);
        const response = await fetch(`${this.config.apiBaseUrl}${path}`, { headers });
        if (!response.ok)
            throw new Error(`Artifact download HTTP ${response.status}`);
        return response;
    }
    chooseFiles(accept, multiple = false) {
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
    fileBase64(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.addEventListener('load', () => {
                const value = String(reader.result ?? '');
                resolve(value.slice(value.indexOf(',') + 1));
            }, { once: true });
            reader.addEventListener('error', () => reject(reader.error), { once: true });
            reader.readAsDataURL(file);
        });
    }
    download(filename, content, mediaType) {
        const blob = content instanceof Blob ? content : new Blob([content], { type: mediaType });
        const link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = filename;
        link.click();
        window.setTimeout(() => URL.revokeObjectURL(link.href), 0);
    }
    static normalizeHttpBase(value) {
        const url = new URL(value ?? window.location.origin, window.location.href);
        if (url.protocol !== 'http:' && url.protocol !== 'https:') {
            throw new Error('apiBaseUrl must use HTTP or HTTPS');
        }
        return url.toString().replace(/\/$/, '');
    }
    static normalizeWebSocketBase(value, httpValue) {
        const http = new URL(httpValue ?? window.location.origin, window.location.href);
        const fallback = `${http.protocol === 'https:' ? 'wss:' : 'ws:'}//${http.host}`;
        const url = new URL(value ?? fallback, window.location.href);
        if (url.protocol !== 'ws:' && url.protocol !== 'wss:') {
            throw new Error('webSocketBaseUrl must use WS or WSS');
        }
        return url.toString().replace(/\/$/, '');
    }
}
