#include <libappindicator/app-indicator.h>
#include <gtk/gtk.h>
#include <stdio.h>

static void selected(GtkMenuItem *item, gpointer data)
{
    (void)item;
    (void)data;
    puts("Clicked actual AppIndicator menu action");
    fflush(stdout);
}

int main(int argc, char **argv)
{
    gtk_init(&argc, &argv);
    AppIndicator *indicator = app_indicator_new("w39-appindicator", "face-smile", APP_INDICATOR_CATEGORY_APPLICATION_STATUS);
    app_indicator_set_title(indicator, "W39 AppIndicator");
    GtkWidget *menu = gtk_menu_new();
    GtkWidget *item = gtk_menu_item_new_with_label("Indicator Action");
    g_signal_connect(item, "activate", G_CALLBACK(selected), NULL);
    gtk_menu_shell_append(GTK_MENU_SHELL(menu), item);
    gtk_widget_show_all(menu);
    app_indicator_set_menu(indicator, GTK_MENU(menu));
    app_indicator_set_status(indicator, APP_INDICATOR_STATUS_ACTIVE);
    gtk_main();
    return 0;
}
