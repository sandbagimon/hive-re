import type {
  SimulationState,
  SimulationStatus,
  ValidationIssue,
} from './types.js';

export interface SimulationStoreState {
  simulationStatus: SimulationStatus;
  simulationState: SimulationState | null;
  validationIssues: ValidationIssue[];
}

type Listener = (state: SimulationStoreState) => void;

const initialState = (): SimulationStoreState => ({
  simulationStatus: 'stopped',
  simulationState: null,
  validationIssues: [],
});

export class SimulationStore {
  private state = initialState();
  private readonly listeners = new Set<Listener>();

  get current(): SimulationStoreState {
    return this.state;
  }

  subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    listener(this.state);
    return () => this.listeners.delete(listener);
  }

  setSimulation(status: SimulationStatus, state: SimulationState | null = null): void {
    this.patch({ simulationStatus: status, simulationState: state });
  }

  setSimulationState(state: SimulationState): void {
    this.patch({ simulationState: state });
  }

  setValidationIssues(validationIssues: ValidationIssue[]): void {
    this.patch({ validationIssues });
  }

  reset(): void {
    this.patch(initialState());
  }

  private patch(values: Partial<SimulationStoreState>): void {
    this.state = { ...this.state, ...values };
    for (const listener of this.listeners) listener(this.state);
  }
}
