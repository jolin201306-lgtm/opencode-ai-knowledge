import type { Plugin } from "@opencode-ai/plugin";

export const ValidateJsonPlugin: Plugin = async ({ client, $, directory }) => {
  return {
    "tool.execute.after": async (input) => {
      if (input.tool !== "write" && input.tool !== "edit") return;

      const args = input.args as Record<string, unknown> | undefined;
      const filePath =
        (args?.file_path as string) ?? (args?.filePath as string) ?? "";

      if (!filePath || !filePath.match(/knowledge[\\\/]articles[\\\/].*\.json$/)) return;

      try {
        const result = await $`python hooks/validate_json.py ${filePath}`.nothrow();

        if (result.exitCode !== 0) {
          const stderr = result.stderr?.toString() ?? "校验失败";
          console.error(`[validate-json] 校验失败: ${filePath}`);
          console.error(stderr);

          try {
            await client.tui.showToast({
              body: {
                title: "JSON 校验失败",
                message: stderr.split("\n").filter(l => l.trim()).slice(0, 2).join(" | "),
                variant: "error",
                duration: 8000,
              },
              query: { directory },
            });
          } catch (toastErr) {
            console.error("[validate-json] Toast 显示失败:", toastErr);
          }
        } else {
          console.log(`[validate-json] 校验通过: ${filePath}`);

          try {
            await client.tui.showToast({
              body: {
                title: "JSON 校验通过",
                message: filePath,
                variant: "success",
                duration: 3000,
              },
              query: { directory },
            });
          } catch (toastErr) {
            console.error("[validate-json] Toast 显示失败:", toastErr);
          }
        }
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : String(err);
        console.error(`[validate-json] 异常: ${message}`);
      }
    },
  };
};
