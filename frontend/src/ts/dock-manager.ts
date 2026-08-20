// Dock manager: renders the binary dock tree from dock-tree.ts into the DOM
// and owns all workspace interaction — tab stacks, splitters, drag & drop with
// five-zone snapping, the panel library modal and layout persistence.

import {
  type DockNode,
  type DropZone,
  type PanelId,
  FALLBACK_LEAF_ID,
  LAYOUT_PRESETS,
  addPanelToLeaf,
  collectPanels,
  createDefaultLayout,
  dropPanel,
  findLeafById,
  findLeafOf,
  firstLeafId,
  removePanel,
  resizeSplit,
  setActive,
  zoneFor,
} from './dock-tree.js';

const DOCK_STORAGE_KEY = 'simlab:dock:v3';

const PANEL_ICONS: Record<string, string> = {
  project: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18"/>',
  assets: '<path d="M3 7l9-4 9 4v10l-9 4-9-4z"/><path d="M3 7l9 4 9-4M12 11v10"/>',
  'scene-tree': '<rect x="3" y="4" width="6" height="4" rx="1"/><rect x="15" y="4" width="6" height="4" rx="1"/><rect x="9" y="16" width="6" height="4" rx="1"/><path d="M6 8v4h12V8M12 12v4"/>',
  viewport: '<path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z"/><path d="M12 12l8-4.5M12 12v9M12 12L4 7.5"/>',
  properties: '<path d="M4 6h16M4 12h16M4 18h16"/><circle cx="9" cy="6" r="1.6"/><circle cx="15" cy="12" r="1.6"/><circle cx="7" cy="18" r="1.6"/>',
  materials: '<path d="M12 3l9 5v8l-9 5-9-5V8z"/><path d="M12 3v18M3 8l9 5 9-5"/>',
  'sim-control': '<path d="M7 5l12 7-12 7z"/>',
  'sim-speed': '<path d="M12 14l4-6"/><circle cx="12" cy="15" r="7"/><path d="M12 12v3l2 2"/>',
  'arm-control': '<circle cx="6" cy="18" r="2"/><path d="M7.5 16.5L14 10M14 10l-2-5 6 3-4 2z"/>',
  'drone-control': '<circle cx="6" cy="6" r="2"/><circle cx="18" cy="6" r="2"/><circle cx="6" cy="18" r="2"/><circle cx="18" cy="18" r="2"/><path d="M7.5 7.5l3.5 3.5M16.5 7.5L13 11M7.5 16.5L11 13M16.5 16.5L13 13"/><rect x="10.5" y="10.5" width="3" height="3" rx="1"/>',
  sensors: '<circle cx="12" cy="12" r="2"/><path d="M7.7 16.3a6 6 0 010-8.6M16.3 7.7a6 6 0 010 8.6M4.9 19.1a10 10 0 010-14.2M19.1 4.9a10 10 0 010 14.2"/>',
  'trajectory-editor': '<path d="M4 18V6M20 18V6"/><path d="M4 14c4 0 4-6 8-6s4 4 8 4"/>',
  recording: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3.5"/>',
  controller: '<path d="M8 6l-5 6 5 6M16 6l5 6-5 6"/>',
  agent: '<path d="M5 5h14a2 2 0 012 2v8a2 2 0 01-2 2h-8l-5 4v-4H5a2 2 0 01-2-2V7a2 2 0 012-2z"/><path d="M8 10h.01M12 10h.01M16 10h.01"/>',
  validation: '<path d="M12 3l8 4v5c0 4.5-3.4 7.7-8 9-4.6-1.3-8-4.5-8-9V7z"/><path d="M8.5 12l2.5 2.5 4.5-4.5"/>',
  console: '<path d="M4 17l5-5-5-5M12 17h8"/>',
  shortcuts: '<circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 114 2c-.9.7-1.5 1.2-1.5 2.3"/><circle cx="12" cy="17" r=".4"/>',
};

const PANEL_DESCRIPTIONS: Record<PanelId, string> = {
  project: 'Create, open and save scene JSON files.',
  assets: 'Browse backend assets and import OpenUSD bundles.',
  'scene-tree': 'Inspect actors, links, joints and sensors.',
  viewport: 'Render, select and transform the active scene.',
  properties: 'Edit transforms and rigid-body properties.',
  materials: 'Apply synchronized physics material presets.',
  'sim-control': 'Run, pause, step, reset and export the model.',
  'sim-speed': 'Choose time scale and inspect measured RTF.',
  'arm-control': 'Jog manipulator joints and return them home.',
  'drone-control': 'Command quadrotor rotor velocities.',
  sensors: 'Inspect live joint, IMU and contact streams.',
  'trajectory-editor': 'Author, save and play joint trajectories.',
  recording: 'Capture and export runtime sensor data.',
  controller: 'Load and monitor a trusted Python controller.',
  agent: 'Collaborate with an agent using the current scene context.',
  validation: 'Review physics preflight issues.',
  console: 'Inspect connection, import and simulation logs.',
  shortcuts: 'Reference camera, selection and workspace controls.',
};

// Where auto-opened panels prefer to land when they are not on screen yet.
const PANEL_HOME_LEAF: Partial<Record<PanelId, string>> = {
  'arm-control': 'right-bottom',
  'drone-control': 'right-bottom',
  properties: 'right-bottom',
  materials: 'right-bottom',
  agent: 'right-bottom',
};

interface PanelMeta {
  root: HTMLElement;
  title: string;
  group: string;
  description: string;
}

interface DragSession {
  panel: PanelId;
  targetLeaf: string | null;
  zone: DropZone | null;
}

export class DockManager {
  private readonly container: HTMLElement;
  private readonly staging: HTMLElement;
  private readonly library: HTMLElement;
  private readonly librarySearch: HTMLInputElement;
  private readonly libraryGroups: HTMLElement;
  private readonly panels = new Map<PanelId, PanelMeta>();
  private readonly userClosed = new Set<PanelId>();
  private root: DockNode | null = null;
  private presetId = 'default';
  private drag: DragSession | null = null;
  private dragGhost: HTMLElement | null = null;
  private libraryTargetLeaf: string | null = null;

  constructor() {
    const find = (id: string): HTMLElement => {
      const value = document.getElementById(id);
      if (!value) throw new Error(`Missing dock element: #${id}`);
      return value;
    };
    this.container = find('dock-root');
    this.staging = find('panel-staging');
    this.library = find('panel-library');
    this.librarySearch = find('panel-library-search') as HTMLInputElement;
    this.libraryGroups = find('panel-library-groups');
    for (const root of this.staging.querySelectorAll<HTMLElement>('[data-panel]')) {
      const id = (root.dataset.panel ?? '') as PanelId;
      if (!id) continue;
      this.panels.set(id, {
        root,
        title: root.dataset.panelTitle ?? id,
        group: root.dataset.panelGroup ?? 'Diagnostics',
        description: PANEL_DESCRIPTIONS[id],
      });
    }
    this.restore();
    this.render();
    this.bindEvents();
    this.renderLibrary();
  }

  // ------------------------------------------------------------------ public

  isOpen(panel: PanelId): boolean {
    return this.root ? collectPanels(this.root).includes(panel) : false;
  }

  openPanel(panel: PanelId, options: { focus?: boolean } = {}): void {
    if (!this.panels.has(panel)) return;
    this.userClosed.delete(panel);
    if (!this.root) this.root = { type: 'leaf', id: 'root-leaf', panels: [], active: null };
    const existing = findLeafOf(this.root, panel);
    if (existing) {
      // Only an explicit focus request activates an already-open panel;
      // default opens must never steal the active tab from other panels.
      if (options.focus) this.root = setActive(this.root, existing.id, panel);
    } else {
      const homeId = PANEL_HOME_LEAF[panel] ?? FALLBACK_LEAF_ID;
      const home = (this.root && findLeafById(this.root, homeId)) ? homeId : firstLeafId(this.root);
      this.root = addPanelToLeaf(this.root, home, panel);
    }
    this.render();
    this.persist();
  }

  closePanel(panel: PanelId): void {
    // The viewport is the workspace anchor. Keeping it mounted prevents canvas
    // teardown and avoids a large geometry jump when surrounding tabs change.
    if (panel === 'viewport') {
      this.focusPanel(panel);
      return;
    }
    if (!this.root) return;
    this.userClosed.add(panel);
    this.root = removePanel(this.root, panel);
    this.render();
    this.persist();
  }

  togglePanel(panel: PanelId): void {
    if (this.isOpen(panel)) this.closePanel(panel);
    else this.openPanel(panel);
  }

  focusPanel(panel: PanelId): void {
    if (!this.root) return;
    const leaf = findLeafOf(this.root, panel);
    if (!leaf) return;
    this.root = setActive(this.root, leaf.id, panel);
    this.render();
    this.persist();
  }

  // Compatibility alias for the previous workspace manager API.
  activateBottomTab(panel: PanelId): void {
    this.focusPanel(panel);
  }

  // Open a panel automatically when its content becomes relevant (robot
  // selected, validation issues, ...). Explicit user closes always win.
  autoOpen(panel: PanelId, relevant: boolean, options: { focus?: boolean } = {}): void {
    if (!relevant || this.userClosed.has(panel)) return;
    const wasOpen = this.isOpen(panel);
    this.openPanel(panel, options);
    if (!wasOpen && !options.focus) return;
  }

  applyPreset(presetId: string): boolean {
    const preset = LAYOUT_PRESETS.find((item) => item.id === presetId);
    if (!preset) return false;
    this.presetId = preset.id;
    this.root = preset.build();
    this.userClosed.clear();
    this.render();
    this.persist();
    return true;
  }

  resetLayout(): void {
    this.applyPreset('default');
  }

  openLibrary(targetLeaf: string | null = null): void {
    this.libraryTargetLeaf = targetLeaf;
    this.librarySearch.value = '';
    this.renderLibrary();
    this.library.hidden = false;
    this.librarySearch.focus();
  }

  closeLibrary(): void {
    this.library.hidden = true;
    this.libraryTargetLeaf = null;
  }

  onChange(callback: () => void): void {
    document.addEventListener('simlab:dock-change', () => callback());
  }

  // ----------------------------------------------------------------- private

  private restore(): void {
    try {
      const saved = JSON.parse(window.localStorage.getItem(DOCK_STORAGE_KEY) ?? 'null') as
        | { root?: DockNode | null; presetId?: string }
        | null;
      if (saved?.root) this.root = saved.root;
      if (saved?.presetId) this.presetId = saved.presetId;
    } catch {
      this.root = null;
    }
    if (!this.root) this.root = createDefaultLayout();
  }

  private persist(): void {
    try {
      window.localStorage.setItem(DOCK_STORAGE_KEY, JSON.stringify({
        root: this.root,
        presetId: this.presetId,
      }));
    } catch {
      // Storage quota or private mode must never break the editor.
    }
    document.dispatchEvent(new CustomEvent('simlab:dock-change'));
  }

  private iconSvg(panel: PanelId): string {
    const body = PANEL_ICONS[panel] ?? '<rect x="4" y="4" width="16" height="16" rx="2"/>';
    return `<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor"
      stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${body}</svg>`;
  }

  private render(): void {
    if (this.drag) return; // never re-render mid-drag
    // Reparent every panel back to staging BEFORE clearing the container:
    // innerHTML = '' would otherwise destroy the mounted panel DOM for good
    // (editor code looks panels up by element id in the live document).
    for (const meta of this.panels.values()) this.staging.appendChild(meta.root);
    this.container.innerHTML = '';
    if (!this.root || collectPanels(this.root).length === 0) {
      this.container.appendChild(this.buildEmptyState());
      return;
    }
    this.container.appendChild(this.buildNode(this.root));
  }

  private buildEmptyState(): HTMLElement {
    const empty = document.createElement('div');
    empty.className = 'dock-empty';
    empty.innerHTML = `
      <p class="dock-empty-title">没有打开的窗口</p>
      <p class="dock-empty-detail">工作区中每个工具都是一个窗口，添加一个开始，或从顶栏恢复布局预设。</p>`;
    const add = document.createElement('button');
    add.type = 'button';
    add.className = 'primary';
    add.textContent = 'Add Window';
    add.addEventListener('click', () => this.openLibrary(null));
    empty.appendChild(add);
    return empty;
  }

  private buildNode(node: DockNode): HTMLElement {
    return node.type === 'leaf' ? this.buildLeaf(node) : this.buildSplit(node);
  }

  private buildSplit(node: Extract<DockNode, { type: 'split' }>): HTMLElement {
    const el = document.createElement('div');
    el.className = `dock-split ${node.direction === 'row' ? 'dock-row' : 'dock-column'}`;
    el.dataset.splitId = node.id;
    node.children.forEach((child, index) => {
      if (index > 0) el.appendChild(this.buildSplitter(node, index - 1));
      const wrapper = document.createElement('div');
      wrapper.className = 'dock-child';
      wrapper.style.flex = `${node.sizes[index] ?? 1} 1 0`;
      wrapper.appendChild(this.buildNode(child));
      el.appendChild(wrapper);
    });
    return el;
  }

  private buildSplitter(node: Extract<DockNode, { type: 'split' }>, index: number): HTMLElement {
    const splitter = document.createElement('div');
    splitter.className = 'dock-splitter';
    splitter.dataset.splitId = node.id;
    splitter.dataset.index = String(index);
    splitter.setAttribute('role', 'separator');
    splitter.title = 'Resize';
    splitter.addEventListener('pointerdown', (event) => {
      event.preventDefault();
      const parent = splitter.parentElement;
      if (!parent) return;
      const extent = (node.direction === 'row' ? parent.clientWidth : parent.clientHeight) || 1;
      const children = [...parent.children].filter((item) => item.classList.contains('dock-child')) as HTMLElement[];
      const before = children[index];
      const after = children[index + 1];
      let last = node.direction === 'row' ? event.clientX : event.clientY;
      document.body.dataset.dragging = 'true';
      const onMove = (move: PointerEvent): void => {
        const position = node.direction === 'row' ? move.clientX : move.clientY;
        const delta = (position - last) / extent;
        last = position;
        if (Math.abs(delta) < 0.0005 || !before || !after) return;
        // Live-resize the two adjacent wrappers; the tree is committed on release.
        const growBefore = Number(before.style.flexGrow || '1') + delta;
        const growAfter = Number(after.style.flexGrow || '1') - delta;
        if (growBefore < 0.08 || growAfter < 0.08) return;
        before.style.flexGrow = String(growBefore);
        after.style.flexGrow = String(growAfter);
      };
      const onUp = (): void => {
        window.removeEventListener('pointermove', onMove);
        window.removeEventListener('pointerup', onUp);
        delete document.body.dataset.dragging;
        if (!this.root) return;
        const fraction = before ? Number(before.style.flexGrow || '1') : 0;
        const oldFraction = node.sizes[index] ?? 1;
        this.root = resizeSplit(this.root, node.id, index, fraction - oldFraction);
        this.render();
        this.persist();
      };
      window.addEventListener('pointermove', onMove);
      window.addEventListener('pointerup', onUp);
    });
    return splitter;
  }

  private buildLeaf(node: Extract<DockNode, { type: 'leaf' }>): HTMLElement {
    const el = document.createElement('section');
    el.className = 'dock-leaf';
    el.dataset.leafId = node.id;
    const active = node.active ?? node.panels[0] ?? null;

    const header = document.createElement('header');
    header.className = 'dock-leaf-tabs';
    const tabs = document.createElement('div');
    tabs.className = 'dock-tabs';
    for (const panel of node.panels) {
      const meta = this.panels.get(panel);
      if (!meta) continue;
      const pinned = panel === 'viewport';
      const tab = document.createElement('div');
      tab.className = `dock-tab ${panel === active ? 'active' : ''} ${pinned ? 'pinned' : ''}`;
      tab.dataset.bottomTab = panel;
      tab.dataset.leafId = node.id;
      tab.innerHTML = `
        <button type="button" class="dock-tab-btn" aria-label="Show ${meta.title} panel">${this.iconSvg(panel)}<span>${meta.title}</span></button>
        ${pinned ? '' : `<button type="button" class="dock-tab-close" data-panel-close="${panel}" title="Close ${meta.title}">✕</button>`}
        <span class="bottom-tab-badge" data-tab-badge="${panel}" hidden></span>`;
      tabs.appendChild(tab);
    }
    header.appendChild(tabs);
    const add = document.createElement('button');
    add.type = 'button';
    add.className = 'dock-leaf-add';
    add.dataset.leafAdd = node.id;
    add.title = 'Add window to this region';
    add.textContent = '+';
    header.appendChild(add);
    el.appendChild(header);

    const body = document.createElement('div');
    body.className = 'dock-leaf-body';
    body.dataset.leafBody = node.id;
    const activeMeta = active ? this.panels.get(active) : null;
    if (activeMeta) body.appendChild(activeMeta.root);
    else {
      const placeholder = document.createElement('div');
      placeholder.className = 'dock-slot-empty';
      placeholder.innerHTML = '<span>Empty region</span><small>Drop a tab here or use + to add a window</small>';
      body.appendChild(placeholder);
    }
    el.appendChild(body);
    return el;
  }

  // ------------------------------------------------------------------ events

  private bindEvents(): void {
    this.container.addEventListener('click', (event) => {
      const target = event.target as HTMLElement;
      const closePanelId = target.closest<HTMLElement>('[data-panel-close]')?.dataset.panelClose;
      if (closePanelId) {
        this.closePanel(closePanelId as PanelId);
        return;
      }
      const addLeafId = target.closest<HTMLElement>('[data-leaf-add]')?.dataset.leafAdd;
      if (addLeafId) {
        this.openLibrary(addLeafId);
        return;
      }
      const tab = target.closest<HTMLElement>('.dock-tab');
      if (tab?.dataset.bottomTab) {
        this.activateTab(tab.dataset.leafId ?? '', tab.dataset.bottomTab as PanelId);
      }
    });

    // Tab drag: a >5px move starts a drag session with a floating ghost chip;
    // releasing over a leaf body drops the panel into the highlighted zone.
    this.container.addEventListener('pointerdown', (event) => {
      const target = event.target as HTMLElement;
      if (target.closest('[data-panel-close], .dock-leaf-add')) return;
      const tab = target.closest<HTMLElement>('.dock-tab');
      if (!tab?.dataset.bottomTab) return;
      const panel = tab.dataset.bottomTab as PanelId;
      if (panel === 'viewport') return;
      const startX = event.clientX;
      const startY = event.clientY;
      let started = false;
      const onMove = (move: PointerEvent): void => {
        if (started) {
          this.updateDrag(move.clientX, move.clientY);
          return;
        }
        if (Math.hypot(move.clientX - startX, move.clientY - startY) <= 5) return;
        started = true;
        cleanup();
        this.beginDrag(panel, move.clientX, move.clientY);
      };
      const onUp = (): void => {
        if (!started) cleanup();
      };
      const cleanup = (): void => {
        window.removeEventListener('pointermove', onMove);
        window.removeEventListener('pointerup', onUp);
      };
      window.addEventListener('pointermove', onMove);
      window.addEventListener('pointerup', onUp);
    });

    // Panel library
    this.library.querySelector('#panel-library-close')?.addEventListener('click', () => this.closeLibrary());
    this.library.addEventListener('click', (event) => {
      if (event.target === this.library.querySelector('.panel-library-scrim')) this.closeLibrary();
      const item = (event.target as HTMLElement).closest<HTMLElement>('[data-library-panel]');
      if (!item?.dataset.libraryPanel) return;
      const panel = item.dataset.libraryPanel as PanelId;
      if (this.isOpen(panel)) {
        this.focusPanel(panel);
      } else if (this.libraryTargetLeaf && this.root) {
        this.root = addPanelToLeaf(this.root, this.libraryTargetLeaf, panel);
        this.render();
        this.persist();
      } else {
        this.openPanel(panel);
      }
      this.closeLibrary();
    });
    this.librarySearch.addEventListener('input', () => this.renderLibrary());
  }

  private activateTab(leafId: string, panel: PanelId): void {
    if (!this.root) return;
    this.root = setActive(this.root, leafId, panel);
    this.render();
    this.persist();
  }

  // -------------------------------------------------------------------- drag

  private beginDrag(panel: PanelId, x: number, y: number): void {
    const meta = this.panels.get(panel);
    this.drag = { panel, targetLeaf: null, zone: null };
    document.body.classList.add('panel-dragging');
    this.dragGhost = document.createElement('div');
    this.dragGhost.className = 'drag-ghost';
    this.dragGhost.textContent = meta?.title ?? panel;
    document.body.appendChild(this.dragGhost);
    this.moveGhost(x, y);
    this.updateDrag(x, y);
    const onMove = (move: PointerEvent): void => this.updateDrag(move.clientX, move.clientY);
    const onUp = (up: PointerEvent): void => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      this.endDrag(up.clientX, up.clientY);
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  }

  private moveGhost(x: number, y: number): void {
    if (!this.dragGhost) return;
    this.dragGhost.style.left = `${x + 12}px`;
    this.dragGhost.style.top = `${y + 14}px`;
  }

  private updateDrag(x: number, y: number): void {
    if (!this.drag) return;
    this.moveGhost(x, y);
    const body = this.leafBodyAt(x, y);
    const leafId = body?.dataset.leafBody ?? null;
    let zone = body ? zoneFor(body.getBoundingClientRect(), x, y) : null;
    // Incoming panels may join the viewport's tab stack, but never split its
    // rectangle. This keeps the render surface stable during window docking.
    if (leafId && this.root && findLeafById(this.root, leafId)?.panels.includes('viewport')) {
      zone = 'center';
    }
    if (leafId === this.drag.targetLeaf && zone === this.drag.zone) return;
    this.clearDropOverlay();
    this.drag.targetLeaf = leafId;
    this.drag.zone = zone;
    if (body && zone) this.showDropOverlay(body, zone);
  }

  private leafBodyAt(x: number, y: number): HTMLElement | null {
    for (const body of this.container.querySelectorAll<HTMLElement>('[data-leaf-body]')) {
      const rect = body.getBoundingClientRect();
      if (x >= rect.left && x <= rect.right && y >= rect.top && y <= rect.bottom) return body;
    }
    return null;
  }

  private showDropOverlay(body: HTMLElement, zone: DropZone): void {
    const veil = document.createElement('div');
    veil.className = 'drop-overlay-veil';
    const rect = document.createElement('div');
    rect.className = `drop-overlay-rect drop-${zone}`;
    body.append(veil, rect);
  }

  private clearDropOverlay(): void {
    for (const item of this.container.querySelectorAll('.drop-overlay-veil, .drop-overlay-rect')) {
      item.remove();
    }
  }

  private endDrag(x: number, y: number): void {
    if (!this.drag) return;
    const { panel, targetLeaf, zone } = this.drag;
    this.drag = null;
    this.dragGhost?.remove();
    this.dragGhost = null;
    document.body.classList.remove('panel-dragging');
    this.clearDropOverlay();
    if (this.root && targetLeaf && zone) {
      this.userClosed.delete(panel);
      this.root = dropPanel(this.root, panel, targetLeaf, zone);
    }
    this.render();
    this.persist();
  }

  // ----------------------------------------------------------------- library

  private renderLibrary(): void {
    const query = this.librarySearch.value.trim().toLowerCase();
    const openPanels = this.root ? collectPanels(this.root) : [];
    const order = ['Scene', 'Viewport', 'Authoring', 'Simulation', 'Robot', 'Data', 'Agent', 'Diagnostics'];
    this.libraryGroups.innerHTML = '';
    for (const group of order) {
      const items = [...this.panels.entries()]
        .filter(([id, meta]) => meta.group === group)
        .filter(([id, meta]) => !query
          || meta.title.toLowerCase().includes(query)
          || id.includes(query))
        .sort((a, b) => a[1].title.localeCompare(b[1].title));
      if (!items.length) continue;
      const heading = document.createElement('div');
      heading.className = 'menu-category';
      heading.textContent = group;
      this.libraryGroups.appendChild(heading);
      for (const [id, meta] of items) {
        const item = document.createElement('button');
        item.type = 'button';
        item.className = 'panel-library-item';
        item.dataset.libraryPanel = id;
        item.innerHTML = `${this.iconSvg(id)}<span class="panel-library-copy"><strong>${meta.title}</strong><small>${meta.description}</small></span>
          <span class="panel-library-check">${openPanels.includes(id) ? '✓ open' : ''}</span>`;
        this.libraryGroups.appendChild(item);
      }
    }
  }
}
