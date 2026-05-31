import Foundation
import Combine

final class AppSession: ObservableObject {
    @Published var apiBaseURL: URL =
        URL(string: ProcessInfo.processInfo.environment["SHINKAI_API_URL"] ?? "http://localhost:8100")!
    @Published var adminToken: String? = nil

    func authorizedRequest(path: String, method: String = "GET", body: Data? = nil) -> URLRequest {
        var request = URLRequest(url: apiBaseURL.appendingPathComponent(path))
        request.httpMethod = method
        if let token = adminToken, !token.isEmpty {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        if let body = body {
            request.httpBody = body
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        return request
    }
}
