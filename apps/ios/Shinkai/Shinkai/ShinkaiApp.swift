import SwiftUI

@main
struct ShinkaiApp: App {
    @StateObject private var session = AppSession()

    var body: some Scene {
        WindowGroup {
            RunListView()
                .environmentObject(session)
        }
    }
}
