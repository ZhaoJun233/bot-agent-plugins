using System.Reflection;
using System.Runtime.Loader;

if (args.Length != 2) throw new ArgumentException("Usage: ContractProbe <host-core.dll> <plugin.dll>");
var core = AssemblyLoadContext.Default.LoadFromAssemblyPath(Path.GetFullPath(args[0]));
var contract = core.GetType("BotAgent.Domain.Plugins.IBotPlugin", throwOnError: true)!;
var contextType = core.GetType("BotAgent.Domain.Plugins.PluginContext", throwOnError: true)!;
var pluginAssembly = AssemblyLoadContext.Default.LoadFromAssemblyPath(Path.GetFullPath(args[1]));
var type = pluginAssembly.GetType("Marketplace.Examples.HelloPlugin", throwOnError: true)!;
if (!contract.IsAssignableFrom(type)) throw new InvalidOperationException("Host contract mismatch.");
var plugin = Activator.CreateInstance(type)!;
foreach (var (property, expected) in new[] { ("Id", "community.example.hello"), ("Version", "1.0.0") })
    if (!Equals(contract.GetProperty(property)!.GetValue(plugin), expected))
        throw new InvalidOperationException($"Metadata mismatch: {property}");
if (!Equals(contract.GetProperty("IsPreset")!.GetValue(plugin), false))
    throw new InvalidOperationException("Community plugin must not be a preset.");
var context = Activator.CreateInstance(contextType, new EmptyServices(), null)!;
var initialize = contract.GetMethod("InitializeAsync", new[] { contextType, typeof(CancellationToken) })!;
await (Task)initialize.Invoke(plugin, new[] { context, (object)CancellationToken.None })!;
await (Task)contract.GetMethod("ShutdownAsync")!.Invoke(plugin, new object[] { CancellationToken.None })!;
Console.WriteLine($"PASS: assignability, metadata, initialize and shutdown against {core.FullName}");

sealed class EmptyServices : IServiceProvider
{
    public object? GetService(Type serviceType) => throw new InvalidOperationException("The inert example must not access services.");
}
