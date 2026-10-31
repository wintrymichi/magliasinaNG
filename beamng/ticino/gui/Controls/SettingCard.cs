using System.Windows;
using System.Windows.Controls;

namespace TicinoServer.Controls;

/// <summary>A row of settings as in the Windows 11 Settings app: an icon, a title with a line of description, and
/// the control on the right (Themes/Controls.xaml).</summary>
public class SettingCard : ContentControl
{
    static SettingCard()
    {
        DefaultStyleKeyProperty.OverrideMetadata(typeof(SettingCard), new FrameworkPropertyMetadata(typeof(SettingCard)));
    }

    public static readonly DependencyProperty GlyphProperty =
        DependencyProperty.Register(nameof(Glyph), typeof(string), typeof(SettingCard), new PropertyMetadata(""));
    public static readonly DependencyProperty HeaderProperty =
        DependencyProperty.Register(nameof(Header), typeof(string), typeof(SettingCard), new PropertyMetadata(""));
    public static readonly DependencyProperty DescriptionProperty =
        DependencyProperty.Register(nameof(Description), typeof(string), typeof(SettingCard), new PropertyMetadata(""));

    public string Glyph { get => (string)GetValue(GlyphProperty); set => SetValue(GlyphProperty, value); }
    public string Header { get => (string)GetValue(HeaderProperty); set => SetValue(HeaderProperty, value); }
    public string Description { get => (string)GetValue(DescriptionProperty); set => SetValue(DescriptionProperty, value); }
}

/// <summary>A message bar (WinUI InfoBar): an icon and a text on a tinted card, with optional buttons as content.</summary>
public class InfoBar : ContentControl
{
    static InfoBar()
    {
        DefaultStyleKeyProperty.OverrideMetadata(typeof(InfoBar), new FrameworkPropertyMetadata(typeof(InfoBar)));
    }

    public static readonly DependencyProperty SeverityProperty =
        DependencyProperty.Register(nameof(Severity), typeof(string), typeof(InfoBar), new PropertyMetadata("Info"));
    public static readonly DependencyProperty TitleProperty =
        DependencyProperty.Register(nameof(Title), typeof(string), typeof(InfoBar), new PropertyMetadata(""));
    public static readonly DependencyProperty MessageProperty =
        DependencyProperty.Register(nameof(Message), typeof(string), typeof(InfoBar), new PropertyMetadata(""));

    /// <summary>Info, Success, Warning or Error.</summary>
    public string Severity { get => (string)GetValue(SeverityProperty); set => SetValue(SeverityProperty, value); }
    public string Title { get => (string)GetValue(TitleProperty); set => SetValue(TitleProperty, value); }
    public string Message { get => (string)GetValue(MessageProperty); set => SetValue(MessageProperty, value); }
}
