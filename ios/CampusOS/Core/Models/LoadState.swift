import Foundation

/// Shared loading status for screens backed by the API.
enum LoadState: Equatable {
    case idle
    case loading
    case loaded
    case failed(String)

    var isLoading: Bool { self == .loading }

    var errorMessage: String? {
        if case .failed(let message) = self { return message }
        return nil
    }
}
