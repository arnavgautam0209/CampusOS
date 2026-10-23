import Foundation
import Security

protocol TokenStore: AnyObject {
    func readToken() -> String?
    func saveToken(_ token: String) throws
    func deleteToken()
}

enum KeychainError: LocalizedError {
    case unexpectedStatus(OSStatus)

    var errorDescription: String? {
        switch self {
        case .unexpectedStatus(let status): return "Couldn't save your sign-in securely (Keychain error \(status))."
        }
    }
}

/// Stores the API token in the iOS Keychain, readable only while this device is unlocked.
final class KeychainTokenStore: TokenStore {
    private let service: String
    private let account = "api-token"

    init(service: String = "com.campusos.app.api") {
        self.service = service
    }

    private var baseQuery: [String: Any] {
        [kSecClass as String: kSecClassGenericPassword,
         kSecAttrService as String: service,
         kSecAttrAccount as String: account]
    }

    func readToken() -> String? {
        var query = baseQuery
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne
        var result: AnyObject?
        guard SecItemCopyMatching(query as CFDictionary, &result) == errSecSuccess,
              let data = result as? Data
        else { return nil }
        return String(data: data, encoding: .utf8)
    }

    func saveToken(_ token: String) throws {
        deleteToken()
        var query = baseQuery
        query[kSecValueData as String] = Data(token.utf8)
        query[kSecAttrAccessible as String] = kSecAttrAccessibleWhenUnlockedThisDeviceOnly
        let status = SecItemAdd(query as CFDictionary, nil)
        guard status == errSecSuccess else { throw KeychainError.unexpectedStatus(status) }
    }

    func deleteToken() {
        SecItemDelete(baseQuery as CFDictionary)
    }
}

/// Used by tests and SwiftUI previews.
final class InMemoryTokenStore: TokenStore {
    private var token: String?

    init(token: String? = nil) {
        self.token = token
    }

    func readToken() -> String? { token }
    func saveToken(_ token: String) throws { self.token = token }
    func deleteToken() { token = nil }
}
