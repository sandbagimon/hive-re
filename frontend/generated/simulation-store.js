const initialState = () => ({
    simulationStatus: 'stopped',
    simulationState: null,
    validationIssues: [],
});
export class SimulationStore {
    state = initialState();
    listeners = new Set();
    get current() {
        return this.state;
    }
    subscribe(listener) {
        this.listeners.add(listener);
        listener(this.state);
        return () => this.listeners.delete(listener);
    }
    setSimulation(status, state = null) {
        this.patch({ simulationStatus: status, simulationState: state });
    }
    setSimulationState(state) {
        this.patch({ simulationState: state });
    }
    setValidationIssues(validationIssues) {
        this.patch({ validationIssues });
    }
    reset() {
        this.patch(initialState());
    }
    patch(values) {
        this.state = { ...this.state, ...values };
        for (const listener of this.listeners)
            listener(this.state);
    }
}
