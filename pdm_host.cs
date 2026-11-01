using System;
using System.IO;
using System.Diagnostics;
using System.Threading;

namespace PdmNativeHost {
    class Program {
        static void Main(string[] args) {
            string baseDir = AppDomain.CurrentDomain.BaseDirectory;
            string appExe = Path.Combine(baseDir, "app", "PDM.exe");
            if (!File.Exists(appExe)) {
                appExe = Path.Combine(baseDir, "PDM.exe");
            }
            if (!File.Exists(appExe)) {
                appExe = Path.Combine(baseDir, "..", "app", "PDM.exe");
            }

            if (!File.Exists(appExe)) {
                return;
            }

            ProcessStartInfo psi = new ProcessStartInfo {
                FileName = appExe,
                Arguments = "--native-host",
                WorkingDirectory = Path.GetDirectoryName(appExe),
                UseShellExecute = false,
                RedirectStandardInput = true,
                RedirectStandardOutput = true,
                RedirectStandardError = false,
                CreateNoWindow = true
            };

            Process proc;
            try {
                proc = Process.Start(psi);
            } catch {
                return;
            }

            if (proc == null) return;

            // Forward stdin -> child process stdin
            Thread inThread = new Thread(() => {
                try {
                    using (Stream cin = Console.OpenStandardInput())
                    using (Stream pin = proc.StandardInput.BaseStream) {
                        byte[] buffer = new byte[8192];
                        int read;
                        while ((read = cin.Read(buffer, 0, buffer.Length)) > 0) {
                            pin.Write(buffer, 0, read);
                            pin.Flush();
                        }
                    }
                } catch {}
            });
            inThread.IsBackground = true;
            inThread.Start();

            // Forward child process stdout -> stdout
            try {
                using (Stream pout = proc.StandardOutput.BaseStream)
                using (Stream cout = Console.OpenStandardOutput()) {
                    byte[] buffer = new byte[8192];
                    int read;
                    while ((read = pout.Read(buffer, 0, buffer.Length)) > 0) {
                        cout.Write(buffer, 0, read);
                        cout.Flush();
                    }
                }
            } catch {}

            try {
                proc.WaitForExit();
            } catch {}
        }
    }
}
