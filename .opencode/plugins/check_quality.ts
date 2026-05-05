import type { Plugin } from "@opencode-ai/plugin";

export const CheckQualityPlugin: Plugin = async ({ client, $, directory }) => {
  return {
    "tool.execute.after": async (input) => {
      if (input.tool !== "write" && input.tool !== "edit") {
        return;
      }

      const args = input.args as Record<string, unknown> | undefined;
      const filePath =
        (args?.file_path as string) ?? (args?.filePath as string) ?? "";

      // 拦截 knowledge/articles/ 下的 JSON 写入
      if (!filePath || !filePath.match(/knowledge[\\\/]articles[\\\/].*\.json$/)) {
        return;
      }

      try {
        const result = await $`python hooks/check_quality.py ${filePath}`.nothrow();

        const output = result.stdout?.toString() ?? "";
        const errors = result.stderr?.toString() ?? "";

        if (result.exitCode !== 0 && output.includes("[C]")) {
          // 提取等级信息
          const gradeMatch = output.match(/\[(\d+)\/100\]\s+\[([ABC])\]/);
          const score = gradeMatch?.[1] ?? "?";
          const grade = gradeMatch?.[2] ?? "C";

          await client.tui.showToast({
            body: {
              title: "质量评级 C 级",
              message: `${filePath} - 得分: ${score}/100 (${grade}级)`,
              variant: "warning",
              duration: 8000,
            },
            query: { directory },
          });
        } else {
          const gradeMatch = output.match(/\[(\d+)\/100\]\s+\[([ABC])\]/);
          const score = gradeMatch?.[1] ?? "?";
          const grade = gradeMatch?.[2] ?? "?";

          await client.tui.showToast({
            body: {
              title: "质量评分完成",
              message: `${filePath} - 得分: ${score}/100 (${grade}级)`,
              variant: "info",
              duration: 5000,
            },
            query: { directory },
          });
        }
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : String(err);
        await client.tui.showToast({
          body: {
            title: "评分脚本异常",
            message: message,
            variant: "warning",
            duration: 5000,
          },
          query: { directory },
        });
      }
    },
  };
};
