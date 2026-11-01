// WPF compiles the XAML first in a temporary project that does not get every implicit using (CS0246 for HttpClient,
// FileInfo on the first CI build): they are written out here.
global using System;
global using System.Collections.Generic;
global using System.IO;
global using System.Linq;
global using System.Net.Http;
global using System.Threading;
global using System.Threading.Tasks;
