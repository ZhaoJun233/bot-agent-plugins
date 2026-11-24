using System.Reflection;
using System.Runtime.Loader;

// Maintainer-only: reflection below executes the selected plugin. Never run on a contributor PR.
if (args.Length >= 1 && args[0] == "--official")
{
    if (args.Length != 7)
        throw new ArgumentException("Usage: ContractProbe --official <contracts-dir> <host-core.dll> <plugin.dll> <entry-type> <id> <version>");
    var contractsDir = Path.GetFullPath(args[1]);
    var hostCorePath = Path.GetFullPath(args[2]);
    var pluginDllPath = Path.GetFullPath(args[3]);
    var officialEntryType = args[4];
    var officialExpectedId = args[5];
    var officialExpectedVersion = args[6];
    var pluginDir = Path.GetDirectoryName(pluginDllPath)!;

    AssemblyLoadContext.Default.Resolving += (_, name) =>
    {
        if (string.IsNullOrWhiteSpace(name.Name)) return null;
        if (string.Equals(name.Name, "BotAgent.Core", StringComparison.OrdinalIgnoreCase))
            return AssemblyLoadContext.Default.LoadFromAssemblyPath(hostCorePath);
        var hostCandidate = Path.Combine(contractsDir, name.Name + ".dll");
        if (File.Exists(hostCandidate))
            return AssemblyLoadContext.Default.LoadFromAssemblyPath(hostCandidate);
        var pluginCandidate = Path.Combine(pluginDir, name.Name + ".dll");
        return File.Exists(pluginCandidate)
            ? AssemblyLoadContext.Default.LoadFromAssemblyPath(pluginCandidate)
            : null;
    };

    var officialCore = AssemblyLoadContext.Default.LoadFromAssemblyPath(hostCorePath);
    var officialContract = officialCore.GetType("BotAgent.Domain.Plugins.IBotPlugin", throwOnError: true)!;
    var officialPluginAsm = AssemblyLoadContext.Default.LoadFromAssemblyPath(pluginDllPath);
    var officialType = officialPluginAsm.GetType(officialEntryType, throwOnError: true)!;
    if (!officialContract.IsAssignableFrom(officialType))
        throw new InvalidOperationException("Official host contract mismatch.");
    var officialPlugin = Activator.CreateInstance(officialType)!;
    foreach (var (property, expected) in new[] { ("Id", officialExpectedId), ("Version", officialExpectedVersion) })
        if (!Equals(officialContract.GetProperty(property)!.GetValue(officialPlugin), expected))
            throw new InvalidOperationException($"Official metadata mismatch: {property}");
    foreach (var property in new[] { "Name", "Description" })
        if (string.IsNullOrWhiteSpace(officialContract.GetProperty(property)!.GetValue(officialPlugin) as string))
            throw new InvalidOperationException($"Official metadata blank: {property}");
    Console.WriteLine($"PASS official: {officialExpectedId}@{officialExpectedVersion} against {officialCore.FullName}");
    return;
}

if (args.Length != 2 && args.Length != 5)
    throw new ArgumentException("Usage: ContractProbe <host-core.dll> <plugin.dll> [<entry-type> <id> <version>]");
var entryType = args.Length == 5 ? args[2] : "Marketplace.Examples.HelloPlugin";
var expectedId = args.Length == 5 ? args[3] : "community.example.hello";
var expectedVersion = args.Length == 5 ? args[4] : "1.0.0";
var core = AssemblyLoadContext.Default.LoadFromAssemblyPath(Path.GetFullPath(args[0]));
var contract = core.GetType("BotAgent.Domain.Plugins.IBotPlugin", throwOnError: true)!;
var contextType = core.GetType("BotAgent.Domain.Plugins.PluginContext", throwOnError: true)!;
var pluginAssembly = AssemblyLoadContext.Default.LoadFromAssemblyPath(Path.GetFullPath(args[1]));
var type = pluginAssembly.GetType(entryType, throwOnError: true)!;
if (!contract.IsAssignableFrom(type)) throw new InvalidOperationException("Host contract mismatch.");
var plugin = Activator.CreateInstance(type)!;
foreach (var (property, expected) in new[] { ("Id", expectedId), ("Version", expectedVersion) })
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
