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
    simulationSceneJson = null;
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
        this.simulationSceneJson = null;
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
                return this.importOpenUsd('file');
            case 'importOpenUsdFolder':
                return this.importOpenUsd('folder');
            case 'getVisualGeometry':
                return this.getVisualGeometry(String(args[0]));
            case 'getVisualGeometryBundle':
                return this.getVisualGeometryBundle(String(args[0]));
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
            case 'discardSimulation':
                await this.discardSimulation();
                return this.success({});
            case 'setSimulationSpeed':
                return this.simulationRequest('/speed', {
                    method: 'PUT', body: JSON.stringify({ factor: Number(args[0]) }),
                });
            case 'setJointTargets':
                await this.synchronizeSceneArgument(args[0]);
                return this.simulationRequest('/joint-targets', {
                    method: 'PUT', body: JSON.stringify({ targets: JSON.parse(String(args[1])) }),
                });
            case 'setActuatorControls':
                await this.synchronizeSceneArgument(args[0]);
                return this.simulationRequest('/actuator-controls', {
                    method: 'PUT', body: JSON.stringify({ controls: JSON.parse(String(args[1])) }),
                });
            case 'setAttachmentCommands':
                await this.synchronizeSceneArgument(args[0]);
                return this.simulationRequest('/attachments', {
                    method: 'PUT', body: JSON.stringify({ commands: JSON.parse(String(args[1])) }),
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
        // The store may still be synchronizing the initial Untitled Scene. Serialize Open behind
        // that write so a late initial response can never overwrite the scene the user selected.
        await this.sceneSync;
        const project = await this.updateScene(await file.text());
        return this.success({ scene: project.scene, path: file.name });
    }
    async saveBrowserProject(sceneJson) {
        await this.sceneSync;
        const project = await this.updateScene(sceneJson);
        const scene = project.scene;
        const safeName = String(scene.name ?? 'scene')
            .replace(/[^a-z0-9_-]+/gi, '-')
            .replace(/^-|-$/g, '') || 'scene';
        const filename = `${safeName}.json`;
        this.download(filename, `${JSON.stringify(scene, null, 2)}\n`, 'application/json');
        return this.success({ path: filename });
    }
    async importOpenUsd(mode) {
        const files = mode === 'folder'
            ? await this.chooseDirectory()
            : await this.chooseFiles('.usd,.usda,.usdc,.usdz,.zip');
        if (!files?.length)
            return { ok: false, error: 'Cancelled' };
        const entries = files.map((file) => ({
            file,
            name: (file.webkitRelativePath || file.name).replace(/\\/g, '/'),
        }));
        const entry = this.selectOpenUsdEntry(entries.map(({ name }) => name));
        if (entry === null)
            return { ok: false, error: 'Cancelled' };
        if (!entry)
            return { ok: false, error: 'No OpenUSD entry file selected' };
        const body = new FormData();
        body.set('entry', entry);
        for (const item of entries)
            body.append('files', item.file, item.name);
        const payload = await this.request(this.projectPath('/assets/openusd'), {
            method: 'POST', body,
        });
        return this.success(payload);
    }
    async getVisualGeometry(artifactId) {
        const payload = await this.request(this.projectPath(`/geometry/${encodeURIComponent(artifactId)}`));
        const [baseColor, normal, roughness, metallic] = await Promise.all([
            this.textureArtifactUrl(payload.base_color_texture),
            this.textureArtifactUrl(payload.normal_texture),
            this.textureArtifactUrl(payload.roughness_texture),
            this.textureArtifactUrl(payload.metallic_texture),
        ]);
        if (baseColor)
            payload.base_color_texture_url = baseColor;
        if (normal)
            payload.normal_texture_url = normal;
        if (roughness)
            payload.roughness_texture_url = roughness;
        if (metallic)
            payload.metallic_texture_url = metallic;
        return this.success(payload);
    }
    async textureArtifactUrl(value) {
        if (typeof value !== 'string' || !value.startsWith('art_'))
            return null;
        const response = await this.requestResponse(`/api/v1/artifacts/${encodeURIComponent(value)}`);
        return URL.createObjectURL(await response.blob());
    }
    async getVisualGeometryBundle(artifactId) {
        const response = await this.requestResponse(`/api/v1/artifacts/${encodeURIComponent(artifactId)}`, { cache: 'force-cache' });
        return this.success(await response.arrayBuffer());
    }
    selectOpenUsdEntry(paths) {
        const candidates = paths
            .filter((path) => /\.(usd|usda|usdc|usdz|zip)$/i.test(path))
            .sort((left, right) => {
            const depth = left.split('/').length - right.split('/').length;
            return depth || left.localeCompare(right);
        });
        if (candidates.length <= 1)
            return candidates[0];
        const shallowestDepth = candidates[0].split('/').length;
        const shallowest = candidates.filter((path) => path.split('/').length === shallowestDepth);
        if (shallowest.length === 1)
            return shallowest[0];
        const selected = window.prompt(`Select the OpenUSD entry file:\n${shallowest.join('\n')}`, shallowest[0]);
        if (selected === null)
            return null;
        const normalized = selected.replace(/\\/g, '/');
        if (!shallowest.includes(normalized)) {
            throw new Error(`Selected OpenUSD entry is not in the upload: ${normalized}`);
        }
        return normalized;
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
        return this.simulationRequest(path, { method: 'POST' }, typeof sceneJson === 'string');
    }
    async simulationRequest(path, init = {}, requireCurrentScene = false) {
        return await this.simulationApi(path, init, requireCurrentScene);
    }
    async simulationApi(path, init = {}, requireCurrentScene = false) {
        const simulationId = await this.ensureSimulation(requireCurrentScene);
        return this.request(`/api/v1/simulations/${encodeURIComponent(simulationId)}${path}`, init);
    }
    async ensureSimulation(requireCurrentScene = false) {
        await this.sceneSync;
        if (this.simulationId
            && requireCurrentScene
            && this.simulationSceneJson !== this.lastSceneJson) {
            await this.discardSimulation();
        }
        if (this.simulationId)
            return this.simulationId;
        const payload = await this.request('/api/v1/simulations', {
            method: 'POST', body: JSON.stringify({ project_id: this.requireProjectId() }),
        });
        this.simulationId = payload.id;
        this.simulationSceneJson = this.lastSceneJson;
        this.applySnapshot(payload.snapshot);
        this.connectWebSocket(payload.id);
        return payload.id;
    }
    async discardSimulation() {
        const simulationId = this.simulationId;
        if (!simulationId)
            return;
        const socket = this.socket;
        this.socket = null;
        socket?.close();
        if (this.reconnectTimer !== null)
            window.clearTimeout(this.reconnectTimer);
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
        if (init.body !== undefined && !(init.body instanceof FormData)) {
            headers.set('Content-Type', 'application/json');
        }
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
    async requestResponse(path, init = {}) {
        if (!this.config)
            throw new Error('Runtime configuration unavailable');
        const headers = new Headers(init.headers);
        if (this.config.accessToken)
            headers.set('Authorization', `Bearer ${this.config.accessToken}`);
        const response = await fetch(`${this.config.apiBaseUrl}${path}`, { ...init, headers });
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
    chooseDirectory() {
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
    download(filename, content, mediaType) {
        const blob = content instanceof Blob ? content : new Blob([content], { type: mediaType });
        const link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = filename;
        link.click();
        window.setTimeout(() => URL.revokeObjectURL(link.href), 0);
    }
    static normalizeHttpBase(value) {
        if (value === 'same-origin')
            return window.location.origin;
        const url = new URL(value ?? window.location.origin, window.location.href);
        if (url.protocol !== 'http:' && url.protocol !== 'https:') {
            throw new Error('apiBaseUrl must use HTTP or HTTPS');
        }
        return url.toString().replace(/\/$/, '');
    }
    static normalizeWebSocketBase(value, httpValue) {
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
