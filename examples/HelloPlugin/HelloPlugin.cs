using BotAgent.Domain.Plugins;

namespace Marketplace.Examples;

// Deliberately inert: no messages, network, files, timers or service discovery.
public sealed class HelloPlugin : IBotPlugin
{
    public string Id => "community.example.hello";
    public string Name => "Hello lifecycle example";
    public string Version => "1.0.0";
    public string Description => "Inert example that demonstrates the plugin lifecycle.";
    public PluginCategory Category => PluginCategory.Feature;
    public bool IsPreset => false;
    public Task InitializeAsync(PluginContext context, CancellationToken ct)
    {
        ct.ThrowIfCancellationRequested();
        return Task.CompletedTask;
    }
    public Task ShutdownAsync(CancellationToken ct) => Task.CompletedTask;
}
