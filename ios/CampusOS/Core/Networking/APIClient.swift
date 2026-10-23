import Foundation

/// Talks to the CampusOS Django REST API (/api/v1/).
/// Authenticated requests send the Keychain token as "Authorization: Token <key>".
final class APIClient {
    let tokenStore: TokenStore
    /// Called on the main actor when the server rejects the saved token.
    var onUnauthorized: (@MainActor () -> Void)?

    private let session: URLSession
    private let baseURL: () -> URL

    init(session: URLSession = .shared,
         tokenStore: TokenStore = KeychainTokenStore(),
         baseURL: @escaping () -> URL = { AppConfig.baseURL }) {
        self.session = session
        self.tokenStore = tokenStore
        self.baseURL = baseURL
    }

    var serverDescription: String {
        let url = baseURL()
        return [url.host, url.port.map(String.init)].compactMap { $0 }.joined(separator: ":")
    }

    func get<T: Decodable>(_ path: String, authenticated: Bool) async throws -> T {
        try await send(path, method: "GET", body: nil, authenticated: authenticated)
    }

    func post<T: Decodable>(_ path: String, body: some Encodable, authenticated: Bool) async throws -> T {
        try await send(path, method: "POST", body: try JSONEncoder.campusOS.encode(body),
                       authenticated: authenticated)
    }

    func post<T: Decodable>(_ path: String, authenticated: Bool) async throws -> T {
        try await send(path, method: "POST", body: nil, authenticated: authenticated)
    }

    private func send<T: Decodable>(_ path: String, method: String, body: Data?,
                                    authenticated: Bool) async throws -> T {
        guard let url = URL(string: path, relativeTo: baseURL()) else { throw APIError.badResponse }
        var request = URLRequest(url: url, timeoutInterval: 15)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if let body {
            request.httpBody = body
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        if authenticated {
            // Public endpoints must not get a token: DRF rejects invalid tokens even there.
            guard let token = tokenStore.readToken() else { throw APIError.notSignedIn }
            request.setValue("Token \(token)", forHTTPHeaderField: "Authorization")
        }

        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: request)
        } catch let error as URLError where error.code != .cancelled {
            throw APIError.unreachable
        }

        guard let http = response as? HTTPURLResponse else { throw APIError.badResponse }
        guard (200...299).contains(http.statusCode) else {
            let error = APIError.from(status: http.statusCode, data: data)
            if error == .unauthorized, authenticated, let onUnauthorized {
                await onUnauthorized()
            }
            throw error
        }
        do {
            return try JSONDecoder.campusOS.decode(T.self, from: data)
        } catch {
            throw APIError.badResponse
        }
    }
}

extension JSONDecoder {
    /// Decodes Django's ISO 8601 dates, with or without microseconds.
    static let campusOS: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .custom { decoder in
            let container = try decoder.singleValueContainer()
            let text = try container.decode(String.self)
            guard let date = ISO8601Parsing.date(from: text) else {
                throw DecodingError.dataCorruptedError(in: container,
                                                       debugDescription: "Invalid date: \(text)")
            }
            return date
        }
        return decoder
    }()
}

extension JSONEncoder {
    static let campusOS: JSONEncoder = {
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        return encoder
    }()
}

enum ISO8601Parsing {
    static func date(from text: String) -> Date? {
        let withFraction = ISO8601DateFormatter()
        withFraction.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = withFraction.date(from: trimmingFraction(text)) { return date }
        return ISO8601DateFormatter().date(from: text)
    }

    /// Django sends microseconds (6 digits); keep milliseconds for the formatter.
    private static func trimmingFraction(_ text: String) -> String {
        guard let dot = text.firstIndex(of: ".") else { return text }
        let digitsStart = text.index(after: dot)
        let digitsEnd = text[digitsStart...].firstIndex { !$0.isNumber } ?? text.endIndex
        let digits = text[digitsStart..<digitsEnd]
        guard digits.count > 3 else { return text }
        return String(text[..<digitsStart]) + digits.prefix(3) + text[digitsEnd...]
    }
}
