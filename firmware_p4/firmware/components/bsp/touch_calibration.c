#include "touch_calibration.h"
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include "esp_log.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "nvs.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "lvgl.h"
#include "esp_lvgl_port.h"

#define CAL_FILE "/data/metadata/touch_calibration.txt"
static const char *TAG = "touch_cal";
static const int tx[4] = {60, 740, 740, 60};
static const int ty[4] = {60, 60, 420, 420};
/* LVGL applies LV_DISP_ROT_90 to every input sample.  Calibrate into its
 * native 480x800 input space, not the visible 800x480 UI space. */
static const int nx[4] = {60, 60, 420, 420};
static const int ny[4] = {739, 59, 59, 739};
static float m[6]; static bool valid, active; static int step; static int64_t last;
static int last_rx = -10000, last_ry = -10000;
static lv_obj_t *label;

static void apply(uint16_t *x, uint16_t *y) {
    float ox = m[0]* *x + m[1]* *y + m[2];
    float oy = m[3]* *x + m[4]* *y + m[5];
    *x = (uint16_t)(ox < 0 ? 0 : ox > 479 ? 479 : ox);
    *y = (uint16_t)(oy < 0 ? 0 : oy > 799 ? 799 : oy);
}
static void fallback(uint16_t *x, uint16_t *y) { (void)x; (void)y; }
static void show_step(void) {
    lv_obj_t *scr=lv_obj_create(NULL); lv_obj_set_style_bg_color(scr,lv_color_hex(0x09090D),0);
    label=lv_label_create(scr); lv_obj_set_style_text_color(label,lv_color_hex(0xFFFFFF),0);
    lv_obj_set_style_text_font(label,&lv_font_montserrat_20,0); char s[96];
    snprintf(s,sizeof(s),"Touch calibration\n\nTap the glowing target %d of 4",step+1); lv_label_set_text(label,s); lv_obj_center(label);
    lv_obj_t *dot=lv_obj_create(scr); lv_obj_set_size(dot,48,48); lv_obj_set_style_radius(dot,LV_RADIUS_CIRCLE,0);
    lv_obj_set_style_bg_color(dot,lv_color_hex(0x00E5FF),0); lv_obj_set_style_border_color(dot,lv_color_hex(0xFFFFFF),0); lv_obj_set_style_border_width(dot,3,0);
    lv_obj_set_pos(dot,tx[step]-24,ty[step]-24); lv_obj_clear_flag(dot,LV_OBJ_FLAG_SCROLLABLE); lv_scr_load_anim(scr, LV_SCR_LOAD_ANIM_NONE, 0, 0, true);
}
static bool solve(float out[3], int *rx, int *ry, const int *v) {
    float a[3][4]={0}; for(int i=0;i<4;i++){ float X=rx[i],Y=ry[i]; float q[3]={X,Y,1}; for(int r=0;r<3;r++){for(int c=0;c<3;c++)a[r][c]+=q[r]*q[c];a[r][3]+=q[r]*v[i];}}
    for(int i=0;i<3;i++){float p=a[i][i];if(p>-0.001f&&p<0.001f)return false;for(int c=i;c<4;c++)a[i][c]/=p;for(int r=0;r<3;r++)if(r!=i){float f=a[r][i];for(int c=i;c<4;c++)a[r][c]-=f*a[i][c];}}
    for(int i=0;i<3;i++) out[i]=a[i][3];
    return true;
}
static bool finish(int *rx,int *ry){ if(!solve(&m[0],rx,ry,nx)||!solve(&m[3],rx,ry,ny)){ESP_LOGE(TAG,"invalid calibration points");return false;} bool saved=false; mkdir("/data/metadata",0755); FILE *f=fopen(CAL_FILE,"w"); if(f){fprintf(f,"RSCAL2 %.7f %.7f %.7f %.7f %.7f %.7f\n",m[0],m[1],m[2],m[3],m[4],m[5]); fclose(f); saved=true;} nvs_handle_t h; if(nvs_open("touch_cal",NVS_READWRITE,&h)==ESP_OK){if(nvs_set_blob(h,"matrix_v2",m,sizeof(m))==ESP_OK&&nvs_commit(h)==ESP_OK)saved=true;nvs_close(h);} if(!saved){ESP_LOGE(TAG,"cannot save calibration");return false;} ESP_LOGI(TAG,"calibration saved"); vTaskDelay(pdMS_TO_TICKS(400)); esp_restart(); return true; }
static void task(void *arg){ static int rx[4],ry[4]; int seen=0; for(;;){if(step>seen){rx[seen]=(int)((uintptr_t*)arg)[seen*2];ry[seen]=(int)((uintptr_t*)arg)[seen*2+1];seen=step;if(step==4){if(finish(rx,ry)) break; step=0; seen=0; last_rx=last_ry=-10000;}lvgl_port_lock(0xffffffff);show_step();lvgl_port_unlock();}vTaskDelay(pdMS_TO_TICKS(40));}vTaskDelete(NULL);}
static uintptr_t raw[8];
bool touch_calibration_start_if_needed(void){FILE*f=fopen(CAL_FILE,"r");char h[8]={0};if(f&&fscanf(f,"%7s %f %f %f %f %f %f",h,&m[0],&m[1],&m[2],&m[3],&m[4],&m[5])==7&&!strcmp(h,"RSCAL2")){fclose(f);valid=true;ESP_LOGI(TAG,"loaded calibration file");return false;}if(f)fclose(f);nvs_handle_t n;size_t len=sizeof(m);if(nvs_open("touch_cal",NVS_READONLY,&n)==ESP_OK){esp_err_t e=nvs_get_blob(n,"matrix_v2",m,&len);nvs_close(n);if(e==ESP_OK&&len==sizeof(m)){valid=true;ESP_LOGI(TAG,"loaded calibration backup");return false;}}active=true;step=0;last_rx=last_ry=-10000;lvgl_port_lock(0xffffffff);show_step();lvgl_port_unlock();xTaskCreate(task,"touch_cal",4096,raw,4,NULL);return true;}
void touch_calibration_process(uint16_t *x,uint16_t*y,uint8_t points){if(!points)return;uint16_t rx=*x,ry=*y;int dx=(int)rx-last_rx,dy=(int)ry-last_ry;if(active&&step<4&&esp_timer_get_time()-last>250000&&(step==0||dx*dx+dy*dy>3600)){raw[step*2]=rx;raw[step*2+1]=ry;last_rx=rx;last_ry=ry;last=esp_timer_get_time();step++;}/* LVGL owns the landscape rotation.  Temporarily pass native GT911 points
 * through unchanged while validating the stored affine matrix. */fallback(x,y);}
