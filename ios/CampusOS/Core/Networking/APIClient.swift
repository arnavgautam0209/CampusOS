import Foundation

struct APIClient {
    // Future: configure an HTTPS Django REST API URL.
    // Never put API secrets or university credentials in source control.
    let session: URLSession = .shared
}
