#if NET10_0_OR_GREATER
using System.Collections.Immutable;
using System.Diagnostics.CodeAnalysis;
using System.Runtime.CompilerServices;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;
using BotAgent.Domain.Conversation;
using BotAgent.Domain.Messaging;
using BotAgent.Domain.Ops;
using BotAgent.Domain.Permissions;
using BotAgent.Domain.Platforms;
using BotAgent.Domain.Plugins;
using BotAgent.Domain.Tools;
using BotAgent.Services.Ops;
using BotAgent.Services.Tools;

[assembly: TypeForwardedTo(typeof(IPluginContribution))]
[assembly: TypeForwardedTo(typeof(IPluginControlContribution))]
[assembly: TypeForwardedTo(typeof(PluginSettingDefinition))]
[assembly: TypeForwardedTo(typeof(PluginSettingsException))]
[assembly: TypeForwardedTo(typeof(AuditEvent))]
[assembly: TypeForwardedTo(typeof(AuditVerification))]
[assembly: TypeForwardedTo(typeof(IAuditChain))]

namespace BotAgent.Domain.Plugins
{
    public interface IPluginContributionSource
    {
        object? GetContribution(Type contract);
    }

    public interface IPluginDependencies
    {
        T Get<T>(string providerId) where T : class, IPluginContribution;
    }

    public readonly record struct ReplyPolicyContext(string SourceKey, bool Proactive, bool DirectMention);

    public interface IReplyPolicyPlugin : IBotPlugin
    {
        string? BlockReason(ReplyPolicyContext context);
    }

    public interface IPluginControlModule
    {
        Task PrepareControlAsync(PluginContext context, CancellationToken ct);
        object? GetControlContribution(Type contract);
        Task ShutdownControlAsync(CancellationToken ct);
    }

    public interface IPluginControlSource
    {
        object? GetControlContribution(Type contract);
    }

    public interface IPluginTwoPhaseLifecycle
    {
        bool RequiresTwoPhaseActivation => true;
        Task PrepareAsync(PluginContext context, CancellationToken ct);
        Task ActivateAsync(CancellationToken ct);
    }
}

namespace BotAgent.Domain.Permissions
{
    public enum ToolCategory
    {
        ConversationRead = 0,
        WebRead = 1,
        OtherConversationRead = 2,
        SendMessage = 3,
        SettingsWrite = 4,
        FileOrShell = 5,
        RemoteAgent = 6,
    }

    public record ToolDescriptor(string Id, ToolCategory Category, string Summary, bool ReadOnly = true)
    {
        public static bool AlwaysDenied(ToolCategory category) => category is
            ToolCategory.OtherConversationRead or ToolCategory.SettingsWrite
            or ToolCategory.FileOrShell or ToolCategory.RemoteAgent;
    }
}

namespace BotAgent.Domain.Tools
{
    public enum ToolOrigin { Builtin = 0, Mcp = 1, Plugin = 2 }

    public static class ToolFeature
    {
        public const string WebSearch = "websearch";
        public const string Music = "music";
        public const string Voice = "voice";
        public const string Stickers = "stickers";
        public const string Poke = "poke";
        public const string Approval = "approval";
        public const string Question = "question";
        public const string Text = "text";
        public const string Documents = "documents";
        public const string Digest = "digest";
        public const string Knowledge = "knowledge";
        public const string Scheduler = "scheduler";
        public const string PersonalTodo = "personal_todo";
    }

    public enum ToolDefaultPolicy
    {
        FollowSwitch = 0,
        AllOnWhenEmpty = 1,
        SafeTierWhenEmpty = 2,
        NamedOnly = 3,
    }

    public sealed record ToolSpec(
        string Id,
        ToolCategory Category,
        string Summary,
        bool ReadOnly,
        string Executor,
        string Parameters,
        ToolDefaultPolicy Default,
        string? Exception = null,
        bool PromptVisible = true,
        string FeatureKey = "",
        ToolOrigin Origin = ToolOrigin.Builtin) : ToolDescriptor(Id, Category, Summary, ReadOnly);

    public readonly record struct ArgsVerdict(bool Ok, string ReasonCode, string? Detail = null)
    {
        public static ArgsVerdict Pass { get; } = new(true, "ok");
        public static ArgsVerdict Fail(string reasonCode, string? detail = null) => new(false, reasonCode, detail);
    }

    public sealed record ArgField(string Name, bool Required = true, int MinLength = 0, int MaxLength = 0);

    public sealed record ToolCall(string ToolId, JsonObject Arguments, int CallIndex = 0);

    public sealed record ToolOutcome(bool Ok, string ReasonCode, string? ModelText = null, string? AuditDetail = null)
    {
        public static ToolOutcome Success(string modelText, string? auditDetail = null)
            => new(true, "ok", modelText, auditDetail);
        public static ToolOutcome Failure(string reasonCode, string modelText, string? auditDetail = null)
            => new(false, reasonCode, modelText, auditDetail);
    }
}

namespace BotAgent.Services.Tools
{
    public interface IToolContribution : IPluginContribution
    {
        public const int CurrentApiVersion = 1;
        ToolDefinition[] DescribeTools();
        Task<ToolOutcome> ExecuteAsync(string sourceKey, ToolCall call, CancellationToken ct);
    }

    public sealed record ToolDefinition(ToolSpec Spec, ImmutableArray<ArgField> Fields, string? HttpUrlField = null);

    public static class ToolArguments
    {
        public static ArgsVerdict Validate(ToolDefinition definition, JsonObject? arguments)
        {
            arguments ??= new JsonObject();
            foreach (var pair in arguments)
                if (!definition.Fields.Any(field => field.Name == pair.Key))
                    return ArgsVerdict.Fail("unknown_field", pair.Key);
            foreach (var field in definition.Fields)
            {
                var node = arguments[field.Name];
                if (node is not null && (node is not JsonValue value || !value.TryGetValue<string>(out _)))
                    return ArgsVerdict.Fail("bad_type", field.Name);
                var text = node?.GetValue<string>()?.Trim() ?? string.Empty;
                if (field.Required && text.Length == 0) return ArgsVerdict.Fail("missing_required", field.Name);
                if (text.Length == 0) continue;
                if (field.MinLength > 0 && text.Length < field.MinLength)
                    return ArgsVerdict.Fail("bad_length", $"{field.Name}<{field.MinLength}");
                if (field.MaxLength > 0 && text.Length > field.MaxLength)
                    return ArgsVerdict.Fail("bad_length", $"{field.Name}>{field.MaxLength}");
            }
            if (definition.HttpUrlField is { } urlField)
            {
                var url = arguments[urlField]?.GetValue<string>()?.Trim() ?? string.Empty;
                if (!url.StartsWith("http://", StringComparison.OrdinalIgnoreCase)
                    && !url.StartsWith("https://", StringComparison.OrdinalIgnoreCase))
                    return ArgsVerdict.Fail("bad_scheme", urlField);
            }
            return ArgsVerdict.Pass;
        }
    }
}

namespace BotAgent.Domain.Conversation
{
    public enum ConversationKind { LocalTest, PrivateChat, GroupChat, ChannelChat }

    public static class MessageMarkers
    {
        public const string AsidePrefix = "〔旁白：";
        public const string AsideSuffix = "〕";
        public static string AsAside(string inner) => AsidePrefix + inner + AsideSuffix;
        public static bool IsAside(string? text)
            => text is not null && text.TrimStart().StartsWith(AsidePrefix, StringComparison.Ordinal);

        public static string EscapeExternalControlTags(string? text)
        {
            if (string.IsNullOrEmpty(text)) return text ?? string.Empty;
            return text
                .Replace("[系统", "［系统", StringComparison.Ordinal)
                .Replace("[system", "［system", StringComparison.OrdinalIgnoreCase)
                .Replace("[assistant", "［assistant", StringComparison.OrdinalIgnoreCase)
                .Replace("[user", "［user", StringComparison.OrdinalIgnoreCase)
                .Replace("[tool", "［tool", StringComparison.OrdinalIgnoreCase)
                .Replace("[已撤回]", "［已撤回］", StringComparison.Ordinal)
                .Replace("[回复 ", "［回复 ", StringComparison.Ordinal)
                .Replace("<system>", "＜system＞", StringComparison.OrdinalIgnoreCase)
                .Replace("<tool>", "＜tool＞", StringComparison.OrdinalIgnoreCase);
        }
    }
}

namespace BotAgent.Domain.Platforms
{
    public static class PlatformId
    {
        public const string QqPrivate = "qq.private";
        public const string QqOfficial = "qq.official";
        public const string Local = "local";
        public const string Feishu = "feishu";

        public static string Normalize(string? platform)
        {
            if (string.IsNullOrWhiteSpace(platform)) return QqPrivate;
            var p = platform.Trim().ToLowerInvariant();
            return p switch
            {
                "private" or "qq" or "onebot" or "qq.private" => QqPrivate,
                "official" or "qq.official" => QqOfficial,
                "local" => Local,
                "feishu" or "lark" => Feishu,
                _ => p,
            };
        }
    }

    public static class AccountScope
    {
        public const string Legacy = "legacy";
        public const string Default = "default";
    }
}

namespace BotAgent.Domain.Messaging
{
    public sealed record ConversationId(
        string PlatformId,
        string AccountScope,
        ConversationKind Kind,
        string NativeTargetId,
        string? ThreadId = null);

    public static class ConversationIdCodec
    {
        public const int MaxKeyLength = 512;
        public static bool TryParse(string? sourceKey, [NotNullWhen(true)] out ConversationId? id)
        {
            id = null;
            if (string.IsNullOrWhiteSpace(sourceKey) || sourceKey.Length > MaxKeyLength) return false;
            if (sourceKey.IndexOfAny(['\r', '\n', '\0']) >= 0) return false;
            if (sourceKey.StartsWith("v=1;", StringComparison.OrdinalIgnoreCase))
            {
                string? platform = null, account = null, kindStr = null, target = null, thread = null;
                foreach (var part in sourceKey.Split(';'))
                {
                    var eq = part.IndexOf('=');
                    if (eq <= 0) continue;
                    var k = part[..eq].Trim();
                    var rawVal = eq + 1 < part.Length ? part[(eq + 1)..].Trim() : string.Empty;
                    string val;
                    try { val = Uri.UnescapeDataString(rawVal); }
                    catch (UriFormatException) { return false; }
                    switch (k.ToLowerInvariant())
                    {
                        case "platform": platform = val; break;
                        case "account": account = val; break;
                        case "kind": kindStr = val; break;
                        case "target": target = val; break;
                        case "thread": thread = string.IsNullOrEmpty(val) ? null : val; break;
                    }
                }
                if (string.IsNullOrWhiteSpace(platform) || string.IsNullOrWhiteSpace(target) || string.IsNullOrWhiteSpace(kindStr))
                    return false;
                ConversationKind kind;
                switch (kindStr.ToLowerInvariant())
                {
                    case "group": kind = ConversationKind.GroupChat; break;
                    case "direct": case "private": kind = ConversationKind.PrivateChat; break;
                    case "channel": kind = ConversationKind.ChannelChat; break;
                    case "local": kind = ConversationKind.LocalTest; break;
                    default: return false;
                }
                id = new ConversationId(PlatformId.Normalize(platform),
                    string.IsNullOrWhiteSpace(account) ? AccountScope.Default : account, kind, target, thread);
                return true;
            }
            string prefix;
            var work = sourceKey;
            if (work.StartsWith("official:", StringComparison.OrdinalIgnoreCase)) { prefix = PlatformId.QqOfficial; work = work["official:".Length..]; }
            else if (work.StartsWith("local:", StringComparison.OrdinalIgnoreCase)) { prefix = PlatformId.Local; work = work["local:".Length..]; }
            else if (work.StartsWith("feishu:", StringComparison.OrdinalIgnoreCase)) { prefix = PlatformId.Feishu; work = work["feishu:".Length..]; }
            else { prefix = PlatformId.QqPrivate; }
            var colon = work.IndexOf(':');
            if (colon <= 0 || colon >= work.Length - 1) return false;
            var tag = work[..colon].ToLowerInvariant();
            var targetId = work[(colon + 1)..].Trim();
            if (string.IsNullOrEmpty(targetId) || targetId.IndexOfAny([':', ';', ' ']) >= 0) return false;
            ConversationKind k2;
            switch (tag)
            {
                case "group": k2 = ConversationKind.GroupChat; break;
                case "private": k2 = ConversationKind.PrivateChat; break;
                default: return false;
            }
            id = new ConversationId(prefix, AccountScope.Legacy, k2, targetId, null);
            return true;
        }
    }
}

namespace BotAgent.Domain.Ops
{
    public readonly record struct TokenUsageSnapshot(
        string TenantId, int UsedPromptTokens, int UsedCompletionTokens, string ResetDate)
    {
        public long UsedTotalTokens => (long)UsedPromptTokens + UsedCompletionTokens;
    }

    public sealed record OperationReceiptWrite(string CallerScope, string IdempotencyKey, string RequestDigest, string State);
}

namespace BotAgent.Domain.Ports
{
    public interface IClock
    {
        DateTimeOffset Now { get; }
        DateTimeOffset UtcNow { get; }
        DateTime LocalDateTime { get; }
        long TickCount { get; }
        Task Delay(TimeSpan delay, CancellationToken ct = default);
        Task Delay(int millisecondsDelay, CancellationToken ct = default);
    }

    public interface IPackageDataStore
    {
        T Read<T>(Func<IPackageDataSession, T> operation);
        T Write<T>(Func<IPackageDataSession, T> operation);
    }

    public interface IPackageDataSession
    {
        object? Scalar(string sql, params PackageDataParameter[] parameters);
        IReadOnlyList<IReadOnlyList<object?>> Query(string sql, params PackageDataParameter[] parameters);
        int Execute(string sql, params PackageDataParameter[] parameters);
        string? ReadState(string key);
        void WriteState(string key, string value);
        TokenUsageSnapshot ReadUsage(string tenantId);
        void AppendAudit(AuditEvent auditEvent);
        void RecordReceipt(OperationReceiptWrite receipt);
    }

    public readonly record struct PackageDataParameter(string Name, object? Value);

    public interface IGroundedTextModel : IPluginContribution
    {
        const string Permission = "model.grounded-text";
        Task<GroundedTextResult> GenerateAsync(GroundedTextRequest request, CancellationToken ct);
    }

    public sealed record GroundedTextRequest(string Prompt, double Temperature, int MaxOutputTokens);
    public sealed record GroundedTextSource(string? Title, string? Url);
    public sealed record GroundedTextResult(string? Text, ImmutableArray<GroundedTextSource> Sources,
        ImmutableArray<string> SearchQueries, string? ErrorCode = null, int? StatusCode = null);
}

namespace BotAgent.Domain.Scheduler
{
    public sealed class CronSchedule
    {
        public static bool TryResolveTimeZone(string? ianaOrId, out TimeZoneInfo timeZone)
            => throw new NotImplementedException("Compile-time shim only");
    }
}

namespace BotAgent.Domain.Stickers
{
    public static class StickerSafetyGuard
    {
        public const long DefaultMaxFileBytes = 10 * 1024 * 1024;
        public static bool TrySanitizeFilename(string? rawFilename, out string safeFilename)
            => throw new NotImplementedException("Compile-time shim only");
        public static bool DetectImageFormat(ReadOnlySpan<byte> header, out string extension, out string mimeType)
            => throw new NotImplementedException("Compile-time shim only");
        public static bool ValidatePayload(ReadOnlySpan<byte> bytes, long maxBytes,
            out string extension, out string mimeType, out string error)
            => throw new NotImplementedException("Compile-time shim only");
    }
}

namespace BotAgent.Services.Voice
{
    public static class VoiceCadence
    {
        public static int IntervalSeconds(int eagerness)
            => throw new NotImplementedException("Compile-time shim only");
    }
}
#endif
