using BotAgent.Domain.Plugins;

namespace Community.PluginTemplate;

public sealed class Plugin : IBotPlugin
{
    public string Id => "community.example.template";
    public string Name => "Community plugin template";
    public string Version => "0.1.0";
    public string Description => "Replace with a clear description of the reviewed functionality.";
    public PluginCategory Category => PluginCategory.Feature;
    public bool IsPreset => false;
    public Task InitializeAsync(PluginContext context, CancellationToken ct) => Task.CompletedTask;
    public Task ShutdownAsync(CancellationToken ct) => Task.CompletedTask;
}
