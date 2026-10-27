// Compile-time contract only. Never distribute this assembly inside a plugin package.
namespace BotAgent.Domain.Plugins;

public enum PluginCategory { Channel, Feature, Media, Management }

public interface IBotPlugin
{
    string Id { get; }
    string Name { get; }
    string Version { get; }
    string Description { get; }
    PluginCategory Category { get; }
    bool IsPreset => true;
    Task InitializeAsync(PluginContext context, CancellationToken ct) => InitializeAsync(ct);
    Task InitializeAsync(CancellationToken ct) => Task.CompletedTask;
    Task ShutdownAsync(CancellationToken ct);
}

public sealed class PluginContext
{
    public IServiceProvider Services { get; }
    public IReadOnlyDictionary<string, string> EnvironmentInfo { get; }
    public PluginContext(IServiceProvider services, IReadOnlyDictionary<string, string>? env = null)
    {
        Services = services ?? throw new ArgumentNullException(nameof(services));
        EnvironmentInfo = env ?? new Dictionary<string, string>();
    }
}
