import Foundation
import Combine

/// Lab catalogue loaded from GET /api/v1/labs/.
@MainActor
final class LabStore: ObservableObject {
    @Published private(set) var labs: [Lab] = []
    @Published private(set) var loadState: LoadState = .idle

    private let fetchLabs: () async throws -> [Lab]

    init(fetchLabs: @escaping () async throws -> [Lab]) {
        self.fetchLabs = fetchLabs
    }

    convenience init(api: APIClient) {
        self.init(fetchLabs: { try await api.get("labs/", authenticated: false) })
    }

    func load() async {
        loadState = .loading
        do {
            labs = try await fetchLabs()
            loadState = .loaded
        } catch {
            // Keep any labs already shown so a failed refresh doesn't blank the screen.
            loadState = .failed(error.localizedDescription)
        }
    }

    func loadIfNeeded() async {
        guard labs.isEmpty, !loadState.isLoading else { return }
        await load()
    }
}
