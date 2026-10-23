import SwiftUI

struct AIPlannerView: View {
    @EnvironmentObject private var planner: PlannerStore
    @EnvironmentObject private var auth: AuthManager
    @EnvironmentObject private var skillPass: SkillPassStore
    @State private var projectIdea = ""
    @State private var showingSignIn = false
    @FocusState private var editorFocused: Bool

    var body: some View {
        Form {
            Section {
                Label("Campus AI Planner", systemImage: "sparkles")
                    .font(.headline)
                Text("Describe your project. CampusOS finds labs, free times, the certifications you need and anything missing, using live campus data.")
                    .font(.subheadline).foregroundStyle(.secondary)
                TextField("e.g. We're building a line-following robot and need soldering tools tomorrow afternoon",
                          text: $projectIdea, axis: .vertical)
                    .lineLimit(4...8)
                    .focused($editorFocused)
                if projectIdea.isEmpty {
                    Button("Try the robot example") { projectIdea = PlannerStore.examplePrompt }
                        .font(.subheadline)
                }
            }

            Section {
                if auth.isSignedIn {
                    Button {
                        editorFocused = false
                        Task { await planner.makePlan(prompt: projectIdea) }
                    } label: {
                        HStack {
                            Spacer()
                            if planner.loadState.isLoading {
                                ProgressView()
                                Text("Planning…").padding(.leading, 6)
                            } else {
                                Label("Plan My Project", systemImage: "wand.and.stars").bold()
                            }
                            Spacer()
                        }
                    }
                    .disabled(projectIdea.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                              || planner.loadState.isLoading)
                } else {
                    Button("Sign In to Plan") { showingSignIn = true }
                        .frame(maxWidth: .infinity)
                }
            } footer: {
                if let message = planner.loadState.errorMessage {
                    Label(message, systemImage: "exclamationmark.triangle.fill")
                        .foregroundStyle(.red)
                }
            }

            if let plan = planner.plan {
                PlanSections(plan: plan)
            }
        }
        .navigationTitle("AI Planner")
        .scrollDismissesKeyboard(.interactively)
        .task(id: auth.isSignedIn) { await skillPass.loadIfNeeded(signedIn: auth.isSignedIn) }
        .sheet(isPresented: $showingSignIn) {
            NavigationStack { SignInView(showsCancel: true) }
        }
        .onAppear {
            if projectIdea.isEmpty, let last = planner.lastPrompt { projectIdea = last }
        }
    }
}
