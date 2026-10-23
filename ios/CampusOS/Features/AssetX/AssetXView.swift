import SwiftUI

struct AssetXView: View {
    var body: some View {
        List {
            Section("Sample inventory") {
                ForEach(DemoLabs.all.flatMap(\.equipment)) { item in
                    HStack {
                        Image(systemName: "shippingbox").foregroundStyle(.orange)
                        VStack(alignment: .leading) {
                            Text(item.name)
                            Text(item.category).font(.caption).foregroundStyle(.secondary)
                        }
                        Spacer()
                        StatusBadge(text: item.isAvailable ? "In stock" : "Unavailable",
                                    color: item.isAvailable ? .green : .red)
                    }
                }
            }
            Section {
                Text("Checkout, return verification and stock forecasting will connect to Django in the next phase.")
                    .foregroundStyle(.secondary)
            }
        }
        .navigationTitle("AssetX")
    }
}
