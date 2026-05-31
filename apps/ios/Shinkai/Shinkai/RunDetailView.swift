import SwiftUI

struct RunDetailView: View {
    @EnvironmentObject var session: AppSession
    let run: Run
    @State private var note: String = ""
    @State private var lastError: String?

    var body: some View {
        Form {
            Section("Run") {
                LabeledContent("Mode", value: run.mode)
                LabeledContent("Status", value: run.status)
                LabeledContent("Stage", value: run.lifecycle_stage)
            }
            Section("Inject guidance") {
                TextEditor(text: $note).frame(height: 100)
                Button("Send injection") {
                    Task { await sendInjection() }
                }
                .disabled(note.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
            if run.status == "awaiting_checkpoint" || run.status == "paused" {
                Section("Checkpoint review") {
                    Button("Approve") { Task { await resolveCheckpoint("approve") } }
                    Button("Modify with note") { Task { await resolveCheckpoint("modify") } }
                        .disabled(note.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    Button("Reject & abort", role: .destructive) {
                        Task { await resolveCheckpoint("reject") }
                    }
                }
            }
            if let lastError = lastError {
                Section { Text(lastError).foregroundStyle(.red) }
            }
        }
        .navigationTitle(run.anchor)
    }

    private func sendInjection() async {
        await postJSON(
            path: "/api/v1/runs/\(run.id)/inject",
            body: ["note": note, "intent": "guidance"]
        )
        note = ""
    }

    private func resolveCheckpoint(_ decision: String) async {
        await postJSON(
            path: "/api/v1/runs/\(run.id)/checkpoint",
            body: ["decision": decision, "note": note]
        )
        note = ""
    }

    private func postJSON(path: String, body: [String: String]) async {
        do {
            let data = try JSONSerialization.data(withJSONObject: body)
            let request = session.authorizedRequest(path: path, method: "POST", body: data)
            let (_, response) = try await URLSession.shared.data(for: request)
            if let httpResp = response as? HTTPURLResponse, !(200...299).contains(httpResp.statusCode) {
                lastError = "HTTP \(httpResp.statusCode)"
            } else {
                lastError = nil
            }
        } catch {
            lastError = error.localizedDescription
        }
    }
}
