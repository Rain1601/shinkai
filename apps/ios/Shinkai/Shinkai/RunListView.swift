import SwiftUI

struct Run: Codable, Identifiable, Hashable {
    let id: String
    let mode: String
    let anchor: String
    let status: String
    let lifecycle_stage: String
}

@MainActor
final class RunListViewModel: ObservableObject {
    @Published var runs: [Run] = []
    @Published var loading = false
    @Published var error: String?

    func refresh(session: AppSession) async {
        loading = true
        defer { loading = false }
        do {
            let request = session.authorizedRequest(path: "/api/v1/runs")
            let (data, _) = try await URLSession.shared.data(for: request)
            self.runs = try JSONDecoder().decode([Run].self, from: data)
        } catch {
            self.error = error.localizedDescription
        }
    }
}

struct RunListView: View {
    @EnvironmentObject var session: AppSession
    @StateObject private var viewModel = RunListViewModel()

    var body: some View {
        NavigationStack {
            List {
                if let error = viewModel.error {
                    Text(error).foregroundStyle(.red)
                }
                ForEach(viewModel.runs) { run in
                    NavigationLink(value: run) {
                        VStack(alignment: .leading) {
                            Text(run.anchor).font(.headline)
                            Text("\(run.mode) · \(run.status) · \(run.lifecycle_stage)")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                }
            }
            .refreshable { await viewModel.refresh(session: session) }
            .navigationDestination(for: Run.self) { run in
                RunDetailView(run: run)
            }
            .navigationTitle("Shinkai")
            .task { await viewModel.refresh(session: session) }
        }
    }
}
