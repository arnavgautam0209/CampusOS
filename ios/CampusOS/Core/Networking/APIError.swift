import Foundation

enum APIError: LocalizedError, Equatable {
    case notSignedIn
    case unauthorized
    case unreachable
    case invalid(String)
    case notFound(String)
    case conflict(String)
    case server(Int)
    case badResponse

    var errorDescription: String? {
        switch self {
        case .notSignedIn: return "Please sign in to continue."
        case .unauthorized: return "Your session has expired. Please sign in again."
        case .unreachable:
            return "Can't reach the CampusOS server. Check that the backend is running and the server address is correct."
        case .invalid(let message), .notFound(let message), .conflict(let message): return message
        case .server(let code): return "The server had a problem (HTTP \(code)). Please try again."
        case .badResponse: return "The server sent a response the app couldn't read."
        }
    }

    /// Maps an HTTP error status and Django REST Framework error body to an APIError.
    static func from(status: Int, data: Data) -> APIError {
        let message = serverMessage(from: data)
        switch status {
        case 400, 422: return .invalid(message ?? "The request was not valid.")
        case 401: return .unauthorized
        case 403: return .invalid(message ?? "You don't have permission to do that.")
        case 404: return .notFound(message ?? "Not found.")
        case 409: return .conflict(message ?? "That conflicts with an existing record.")
        default: return .server(status)
        }
    }

    /// DRF errors look like {"detail": "..."} or {"field": ["..."]}; pick the first message.
    /// File uploads add {"errors": [{"row": 3, "message": "..."}]}: those lines are listed under the detail.
    static func serverMessage(from data: Data) -> String? {
        guard let json = try? JSONSerialization.jsonObject(with: data) else { return nil }
        let message = firstMessage(in: json)
        if let object = json as? [String: Any], let rows = object["errors"] as? [[String: Any]], !rows.isEmpty {
            let lines = rows.prefix(20).compactMap { row -> String? in
                guard let text = row["message"] as? String else { return nil }
                return (row["row"] as? Int).map { "Line \($0): \(text)" } ?? text
            }
            let more = rows.count > 20 ? "\n…and \(rows.count - 20) more" : ""
            return ([message].compactMap { $0 } + lines).joined(separator: "\n") + more
        }
        return message
    }

    private static func firstMessage(in value: Any) -> String? {
        if let text = value as? String { return text }
        if let list = value as? [Any] { return list.lazy.compactMap(firstMessage).first }
        if let object = value as? [String: Any] {
            if let detail = object["detail"], let text = firstMessage(in: detail) { return text }
            for key in object.keys.sorted() {
                if let value = object[key], let text = firstMessage(in: value) { return text }
            }
        }
        return nil
    }
}
