import Foundation

/// Where the CampusOS Django API lives. Editable on the sign-in screen so a
/// physical iPhone can point at the Mac's LAN address during the hackathon.
enum AppConfig {
    static let defaultBaseURL = URL(string: "http://127.0.0.1:8000/api/v1/")!
    private static let baseURLKey = "campusos_api_base_url"

    static var baseURL: URL {
        UserDefaults.standard.string(forKey: baseURLKey).flatMap(normalizedBaseURL) ?? defaultBaseURL
    }

    /// Saves the server address. Returns false if it isn't a usable http(s) URL.
    @discardableResult
    static func setBaseURL(_ text: String) -> Bool {
        guard let url = normalizedBaseURL(text) else { return false }
        UserDefaults.standard.set(url.absoluteString, forKey: baseURLKey)
        return true
    }

    /// Accepts "192.168.1.20:8000", "http://host:8000" or a full ".../api/v1/" URL.
    static func normalizedBaseURL(_ text: String) -> URL? {
        var value = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !value.isEmpty else { return nil }
        if !value.contains("://") { value = "http://" + value }
        guard var components = URLComponents(string: value),
              let scheme = components.scheme?.lowercased(), ["http", "https"].contains(scheme),
              let host = components.host, !host.isEmpty
        else { return nil }

        var path = components.path
        if !path.hasSuffix("/") { path += "/" }
        if path == "/" { path = "/api/v1/" }
        components.path = path
        return components.url
    }
}
