import Foundation

// Ready for Django integration. No network call runs in the demo app.
struct APIClient {
    let baseURL: URL

    init(baseURL: URL = URL(string: "http://127.0.0.1:8000/api/v1/")!) {
        self.baseURL = baseURL
    }

    func get<T: Decodable>(_ path: String, as type: T.Type) async throws -> T {
        let url = baseURL.appendingPathComponent(path)
        var request = URLRequest(url: url)
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode)
        else { throw URLError(.badServerResponse) }
        return try JSONDecoder().decode(T.self, from: data)
    }
}
