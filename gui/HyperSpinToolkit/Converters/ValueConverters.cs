using System.Globalization;
using System.Windows.Data;
using System.Windows.Media;

namespace HyperSpinToolkit.Converters;

[ValueConversion(typeof(bool), typeof(string))]
public class BoolToOkConverter : IValueConverter
{
    public object Convert(object value, Type t, object p, CultureInfo c)
        => value is true ? "✓" : "✗";
    public object ConvertBack(object v, Type t, object p, CultureInfo c) => throw new NotSupportedException();
}

[ValueConversion(typeof(bool), typeof(Brush))]
public class BoolToColorConverter : IValueConverter
{
    public object Convert(object value, Type t, object p, CultureInfo c)
        => new SolidColorBrush(value is true
            ? Color.FromRgb(0x22, 0xc5, 0x5e)
            : Color.FromRgb(0xef, 0x44, 0x44));
    public object ConvertBack(object v, Type t, object p, CultureInfo c) => throw new NotSupportedException();
}

[ValueConversion(typeof(bool), typeof(bool))]
public class InverseBoolConverter : IValueConverter
{
    public object Convert(object value, Type t, object p, CultureInfo c) => value is false;
    public object ConvertBack(object v, Type t, object p, CultureInfo c) => throw new NotSupportedException();
}

[ValueConversion(typeof(string), typeof(Brush))]
public class HexColorToBrushConverter : IValueConverter
{
    public object Convert(object value, Type t, object p, CultureInfo c)
    {
        if (value is string hex)
            try { return (SolidColorBrush)new BrushConverter().ConvertFrom(hex)!; } catch { }
        return Brushes.Gray;
    }
    public object ConvertBack(object v, Type t, object p, CultureInfo c) => throw new NotSupportedException();
}

[ValueConversion(typeof(bool), typeof(System.Windows.Visibility))]
public class BoolToVisibilityConverter : IValueConverter
{
    public object Convert(object value, Type t, object p, CultureInfo c)
        => value is true ? System.Windows.Visibility.Visible : System.Windows.Visibility.Collapsed;
    public object ConvertBack(object v, Type t, object p, CultureInfo c) => throw new NotSupportedException();
}
