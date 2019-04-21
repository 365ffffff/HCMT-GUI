# -*- coding: utf-8 -*-
"""
Created on Sat Mar 23 08:41:45 2019

Automatic Correction System of Weld Bead V2.4

名称：焊道自动纠偏系统V2.4

作者: 尚明安

最后修改日期：201900404 14：34
"""
'''
工控电脑：I7-5500 8G 256G SSD  500万CCD彩色摄像头USB2.0配4mm镜头手动调焦手动光圈CGimagetech
系统：WIN7 X64
开发语言：python , opencv
开发环境：anaconda3 python3.7.1  opencv4.0.1
'''
#tkinter的GUI程序



import tkinter.messagebox
from tkinter import *
from tkinter import scrolledtext
import tkinter
import cv2
import numpy as np
import socket
from PIL import Image,ImageTk
from time import ctime
from threading import Thread
#from PyQt5 import sip

########显示窗口初始化

window = tkinter.Tk()
window.title("HCMT焊道自动纠偏系统V2.4")
window.config(cursor="arrow")


###############下面是一个TCPIP连接的服务端
HOST = '' 
PORT = 8668#本机的端口号
BUFSIZ = 1024
ADDR=(HOST,PORT)
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.bind(ADDR)
s.listen(5)#同时等待5个连接，不是只允许5个连接
s_conn_pool=[]#存放连接到的客户端
c=''#连接上的客户端
local_IP_addr='test version'
PLC_addr='test version'

##############################

#调用USB摄像头，所以参数为0，如果有其他的摄像头可以调整参数为1，2
cap=cv2.VideoCapture(0)#'Movie1.avi'
set_height=480#设置摄像头的分辨率的高
set_width=640#设置摄像头的分辨率的高
cap.set(cv2.CAP_PROP_FRAME_HEIGHT,set_height)#设置摄像头的分辨率为960*640
cap.set(cv2.CAP_PROP_FRAME_WIDTH,set_width)

################################

recordvideo_seconds=5#这是录像的时长5秒，
framecount=1#记录总共接收了多少帧
col_counts=np.array([-1])#找到canny图像中的目标焊道边缘，并记录在这个数组中

col_drawline=-1#记录下输出的值，为-1时为开机后还没有识别出,最多存5个取的平均值
findline_pixcels_setvalue=30#寻找CANNY图中列中含用的白像素个数，大于这个数就认为是边
img=[]
gray=[]
canny=[]

bilateralfilter_var_1=30#双边滤波第一个参数，模糊度
bilateralfilter_var_2=90#双边滤波第一个参数，上限值
bilateralfilter_var_3=80#双边滤波第一个参数，下限值

canny_var_1=50#canny第一个参数，门限值
canny_var_2=200#canny第一个参数，连续度

parameter_names=[]#读取配置文件的参数名到列表
parameter_values=[]#读取配置文件的参数值到列表
read_setupfile_status=0#判断读取配置文件是不是成功了




############################################
connect_status='RUN  Connected'
ErrorCode=0#当发生连接断开后变成1，重新连接上后变0
ErrorCounts=0#当发生连接断开的异常时加1，记录异常的次数



################连接PLC等客户端
def waiting_for_connecting():
    
    global c
    global PLC_addr
    global local_IP_addr
    global s
    
    print('waiting for connecting...')
    status_scrolledtext.insert(tkinter.END,(format(ctime()))[4:20]+'等待连接...'+'\n')
    status_scrolledtext.see(tkinter.END)
    
    c, PLC_addr = s.accept()#这时程序会挂起，不往下执行,直到连接正常后再进行
    print('..connected from:', PLC_addr)
    
    PCname = socket.getfqdn(socket.gethostname(  ))#获取计算机名
    local_IP_addr = socket.gethostbyname(PCname)#获取本机IP，现在只是网口的静态IP，还要想办法获取无线和DHCP的
    status_scrolledtext.insert(tkinter.END,(format(ctime()))[4:20]+'连接上了'+format(PLC_addr)+'\n')
    status_scrolledtext.see(tkinter.END)
    #print (PCname)
    #print (local_IP_addr)

#####################################打开配置文件，读取参数，每次关闭程序时保存关闭前的参数
def read_setup_file():
    
    global parameter_names
    global parameter_values
    global read_setupfile_status
    
    try:
        
        setup_file=open('HCMT_Weld_Bead_Rectification_System.ini',mode='r')
        setup_file_lines=setup_file.readlines()#读模式这两个read()和readlines()谁在前先读到，后面的读到空
        setup_file.close()
        
        for line in setup_file_lines:
            #line是个string
            parameter_names.append(line[0:line.find('=')+1])
            parameter_values.append(line[line.find('=')+1:line.find('\n')])
            
        read_setupfile_status=1    
        print('parameter_names=',parameter_names,'parameter_values=',parameter_values)
        status_scrolledtext.insert(tkinter.END,(format(ctime()))[4:20]+'读取配置文件成功！'+'\n')
        status_scrolledtext.see(tkinter.END)
    except FileNotFoundError:
        print ("Setup_file File is not found.")
        status_scrolledtext.insert(tkinter.END,(format(ctime()))[4:20]+'没有读取到配置文件'+'\n')
        status_scrolledtext.see(tkinter.END)


####################开一个新线程来接收客户端的连接，这样程序就不会一直等待连接而不往下执行
def accept_client():
    #接收新连接
    #while True:
    global s_conn_pool
    print('waiting for connecting...')
    c, PLC_addr = s.accept()#这时程序会挂起，不往下执行,直到连接正常后再进行
    s_conn_pool.append(c)#将客户端放到连接池中
    thread=Thread(target=message_handle,args=(c,))#给每个客户端开一线程
    thread.setDaemon(True)#设置成守护线程，当主线程关闭时这个也关闭
    thread.start()#启动线程
   
    print('..connected from:', PLC_addr)
        
###################处理客户端消息    
def message_handle(client):
    #处理客户端的消息
    global s_conn_pool    
    while True:
        recv_bytes=client.recv(1024)
        print('客户消息：',recv_bytes.decode(encoding='utf8'))
        if len(recv_bytes)==0:
            client.close()
            s_conn_pool.remove(client)
            print('a client is offline')
            break
    
##############监听响应，分辨率的高和宽值的输入值并按回车了，执行这个
def set_resolution_value(event):
    global set_height
    global set_width
    global cap
    
    
    set_height=int(set_height_entry.get())
    set_width=int(set_width_entry.get())
    
#    set_height_entry.delete(0,END)
#    window.update()
#    print(findline_pixcels_value.get())
    #调用USB摄像头，所以参数为0，如果有其他的摄像头可以调整参数为1，2
    cap=cv2.VideoCapture(0)#'Movie1.avi'

    cap.set(cv2.CAP_PROP_FRAME_HEIGHT,set_height)#设置摄像头的分辨率为960*640
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,set_width)
    
#    set_height_entry.insert(0,format(set_height))
#    window.update()

    print('分辨率值,变成了＝',set_height,'X',set_width)
    status_scrolledtext.insert(tkinter.END,(format(ctime()))[4:20]+'分辨率值,变成了＝'+format(set_height)+'X'+format(set_width)+'\n')
    status_scrolledtext.see(tkinter.END)
    
    
 ##############监听响应，bilateralfilter参数值的输入值并按回车了，执行这个
def set_bilateralfilter_var(event):
    global bilateralfilter_var_1
    global bilateralfilter_var_2
    global bilateralfilter_var_3
    
    bilateralfilter_var_1=int(bilateralfilter_entry1.get())
    bilateralfilter_var_2=int(bilateralfilter_entry2.get())
    bilateralfilter_var_3=int(bilateralfilter_entry3.get())
#    print(findline_pixcels_value.get())
    print('bilateralfilter值,变成了＝',bilateralfilter_var_1,' ',bilateralfilter_var_2,' ',bilateralfilter_var_3)
    status_scrolledtext.insert(tkinter.END,(format(ctime()))[4:20]+'bilateralfilter值,变成了＝'+format(bilateralfilter_var_1)+' '+format(bilateralfilter_var_2)+' '+format(bilateralfilter_var_3)+'\n')
    status_scrolledtext.see(tkinter.END)
    
 ##############监听响应，canny参数值的输入值并按回车了，执行这个
def set_canny_var(event):
    global canny_var_1
    global canny_var_2
    canny_var_1=int(canny_entry1.get())
    canny_var_2=int(canny_entry2.get())
#    print(findline_pixcels_value.get())
    print('CANNY参数值,变成了＝',canny_var_1,' ',canny_var_2)
    status_scrolledtext.insert(tkinter.END,(format(ctime()))[4:20]+'CANNY参数值,变成了＝'+format(canny_var_1)+' '+format(canny_var_2)+'\n')
    status_scrolledtext.see(tkinter.END)


##############监听响应，检测边缘的像素限值的输入值并按回车了，执行这个
def set_findline_pixcels_setvalue(event):
    global findline_pixcels_setvalue
    findline_pixcels_setvalue=int(findline_pixcels_value.get())
#    print(findline_pixcels_value.get())
    print('检测边缘的像素限值,变成了＝',findline_pixcels_setvalue)
    status_scrolledtext.insert(tkinter.END,(format(ctime()))[4:20]+'检测边缘的像素限值,变成了＝'+format(findline_pixcels_setvalue)+'\n')
    status_scrolledtext.see(tkinter.END)
    
##############监听响应，录像时长的输入值并按回车了，执行这个
def set_recordvideo_seconds(event):
    global recordvideo_seconds
    recordvideo_seconds=int(recordvideo_seconds_set_entry.get())
#    print(findline_pixcels_value.get())
    print('录像时长,变成了＝',recordvideo_seconds)
    status_scrolledtext.insert(tkinter.END,(format(ctime()))[4:20]+'录像时长,变成了＝'+format(recordvideo_seconds)+'\n')
    status_scrolledtext.see(tkinter.END)
    

######################截图按钮的响应，截下三张图
def take_snapshot():
    
    global img
    global gray
    global canny
    

    grayfilename="grayimageV2.0GUI"+format(ctime())+'.jpg'
    cannyfilename="cannyimageV2.0GUI"+format(ctime())+'.jpg'
    imgfilename="originalimageV2.0GUI"+format(ctime())+'.jpg'
    #print(grayfilename)
    grayfilename=grayfilename.replace(':','_')
    cannyfilename=cannyfilename.replace(':','_')
    imgfilename=imgfilename.replace(':','_')

    #print(grayfilename)
    cv2.imwrite(grayfilename,gray)#str(grayfilename),gray)
    cv2.imwrite(cannyfilename,canny)
    cv2.imwrite(imgfilename,img)
    print("已保存截图grayimageV2.0GUI.jpg和cannyimageV2.0GUI.jpg和originalimageV2.0GUI.jpg")
    
    status_scrolledtext.insert(tkinter.END,(format(ctime()))[4:20]+"已保存截图grayimageV2.0GUI.jpg和cannyimageV2.0GUI.jpg和originalimageV2.0GUI.jpg"+'\n')
    status_scrolledtext.see(tkinter.END)
    
    
######################录制视频
def record_video():
    global recordvideo_seconds


    # 设置帧率
    fps = 20
    # 获取窗口大小
    size = (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
     
    # 设置VideoWrite的信息
    filename='MySaveVideo'+format(ctime())+'.avi'
    filename=filename.replace(':','_')
    videoWrite = cv2.VideoWriter(filename, cv2.VideoWriter_fourcc('I', '4', '2', '0'), fps, size)
     
    # 先获取一帧，用来判断是否成功调用摄像头
    success, frame = cap.read()
    # 通过设置帧数来设置时间,减一是因为上面已经获取过一帧了
    numFrameRemainling = fps * recordvideo_seconds - 1
    while success and numFrameRemainling > 0:
                
        videoWrite.write(frame)
#        cv2.imshow('original',frame)
        success, frame = cap.read()
        numFrameRemainling -= 1
        print('numFrameRemainling=',numFrameRemainling)
        
    print("已保存录像MySaveVideo.avi")
    status_scrolledtext.insert(tkinter.END,(format(ctime()))[4:20]+"已保存录像MySaveVideo.avi"+'\n')
    status_scrolledtext.see(tkinter.END)
    
######################循环取摄像头的图像并显示和检测
def video_loop():
    global img
    global gray
    global canny
    success, img = cap.read()  # 从摄像头读取照片
    global framecount
    global col_counts
    global connect_status
    global ErrorCode
    global ErrorCounts
    global c,s
    global col_drawline
    global findline_pixcels_setvalue
    global bilateralfilter_var_1
    global bilateralfilter_var_2
    global bilateralfilter_var_3
    global canny_var_1
    global canny_var_2
    global panel

    
    if success:
        t_on=cv2.getTickCount()#记录下程序运行到这时刻的时间单位ms
     
    
        #循环从摄像头读取图片
        success,img=cap.read()#得到原始图像
       
    
    
        gray=cv2.cvtColor(img,cv2.COLOR_BGR2GRAY)#转为灰度图片
        bilateralfilter=cv2.bilateralFilter(gray,
                                            bilateralfilter_var_1,
                                            bilateralfilter_var_2,
                                            bilateralfilter_var_3)#,30,90,80双边滤波，模糊度，30，90，80
        canny=cv2.Canny(bilateralfilter,canny_var_1,canny_var_2)#,50,200, apertureSize=3，50是灵敏度，200是长度吧
    #    print(canny.shape)
    #    print(canny[:,0].size)
        column=canny.shape#获出CANNY的图像宽高（480，640）
        #检测CANNY图像的每一列数组识别出焊道的边缘，并将列号放到col_counts 中
    #    print(col_counts)
        for col in range(column[1]):
    #        print(col)
            col_canny=canny[:,col]
            col_pixcels=(col_canny.sum())/255
            if col_pixcels >= findline_pixcels_setvalue:#如果这一列的白像素点有30个以上就认为是焊道边缘
                if col_counts[0] == -1:#如果第一个值是-1那么就认为是开始了
                    col_counts[0]=col
                if col_counts.size <= 4:
                    if col_counts[-1] != col:
                        col_counts=np.append(col_counts,col)
                if col_counts.size >= 5:#只保留5个值，多了就删除第一个
                    col_counts=np.delete(col_counts,[0])
                    col_counts=np.append(col_counts,col)
                           
    #            print('column=',col,'pixcels=',col_pixcels)
                #用红色垂线画出找到的那些列
                lineRED=cv2.line(img,(col,0),(col,column[0]),(0,0,255),1)#画直线到图片,图片,起点,终点,颜色,粗细
    #            print(col_counts)
        col_drawline=col_counts.sum()/col_counts.size
    #    print(col_counts.size)
        #画出从5个边缘的平均列号所在的位置，用绿线
        lineGREEN=cv2.line(img,(int(col_drawline),0),(int(col_drawline),column[0]),(0,255,0),2)#画直线到图片,图片,起点,终点,颜色,粗细
    #    print(c._closed,s._closed)s.dup
        print(format(int(col_drawline)))
        output_pixcel_var.set(format(int(col_drawline)))
#        status_scrolledtext.insert(tkinter.END,format(int(col_drawline))+'\n')
###################################################        
        
        try:
            c.send((format(int(col_drawline))).encode())#将识别出的列号取平均值后发出去
        except (IOError ,ZeroDivisionError) :
            print('disconnected')
            connect_status='STOP  Disconnected'
            
            c.close
            s.close
            if ErrorCode==1 and ErrorCounts==0:
    #            box=tkinter.messagebox.showinfo("提示信息","现PLC的连接中断了，请数检查并重新连接")
            
                print('waiting for connecting...')
                status_scrolledtext.insert(tkinter.END,(format(ctime()))[4:20]+'等待连接...'+'\n')
                status_scrolledtext.see(tkinter.END)
                c, addr = s.accept()#这时程序会挂起，不往下执行,直到连接正常后再进行
                print('..connected from:', addr)
                status_scrolledtext.insert(tkinter.END,(format(ctime()))[4:20]+'连接上了'+format(PLC_addr)+'\n')
                status_scrolledtext.see(tkinter.END)
                connect_status='RUN  Connected'
                ErrorCounts=1
            if ErrorCode==0 and ErrorCounts==0:
                ErrorCode=1
                
                #print('one more')
                connect_status='STOP  Disconnected'
            if ErrorCode==1 and ErrorCounts==1:
                ErrorCode=0
                ErrorCounts=0
            
#############################################
            
        
        t_off=cv2.getTickCount()#记录下程序运行到这时刻的时间单位ms
        framecount=framecount+1#累加帧数
        time=(t_off-t_on)#/1000#/cv2.getCPUTickCount()#算出程序运行到这里用的时间
        #print(time)
        fps=time/10000#算出帧率
        fps=round(fps,2)#帧率保留两个小数位
    #    print('t=',t,'time=',time,'fcount=',framecount,'fps',fps)
    
            
        #处理一下要显示在原始图像上的值
        DisplayFPS='FPS='+format(fps)
        Displayframecount='FrameCounts='+format(framecount)
        DisplayActualValue='Output Value='+format(round(col_drawline,0))
        if connect_status=='STOP  Disconnected':
            status_font_color=(255,0,0)
            
        else:
            status_font_color=(255,255,255)
        DisplaySTATUS='STATUS='+connect_status
    
        #将文字框加入到图片中，(5,20)定义了文字框左顶点在窗口中的位置，字体，大小，最后参数定义文字颜色,粗细
        cv2.putText(img, DisplayFPS, (10, 20),cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        cv2.putText(img, Displayframecount, (10, 40),cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        cv2.putText(img, "SET VALUE=300", (10, 60),cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        cv2.putText(img, DisplayActualValue, (10, 80),cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        cv2.putText(img, "BEAD=3", (10, 100),cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        cv2.putText(img, DisplaySTATUS, (10, 120),cv2.FONT_HERSHEY_SIMPLEX, 0.5, status_font_color, 1)
        line=cv2.line(img,(5,0),(5,120),(255,255,255),1)#画直线到图片,图片,起点,终点,颜色,粗细
    
      
    
    
        cv2.waitKey(0)
        cv2image = cv2.cvtColor(img, cv2.COLOR_BGR2RGBA)#转换颜色从BGR到RGBA
        current_image = Image.fromarray(cv2image)#将图像转换成Image对象
        imgtk = ImageTk.PhotoImage(image=current_image)
        panel.imgtk = imgtk
        panel.config(image=imgtk)
        window.after(1, video_loop)


#camera = cv2.VideoCapture(0)    #摄像头

#window = tkinter.Tk()
#window.title("HCMT焊道纠偏系统V1.3")
##window.protocol('WM_DELETE_WINDOW', detector)
#window.config(cursor="arrow")

#########################################
#下面是把主窗口分成h上下两部分
root_frame=tkinter.Frame(window)#将整个窗口做一个容器
up_window=tkinter.Frame(root_frame)#上半窗口
down_window=tkinter.Frame(root_frame)#下半窗口


setup_frame=tkinter.Frame(up_window,bg='yellow')#左上角设置参数用的容器
#setup_frame.geometry('500x300')  # 这里的乘是小x
image_frame=tkinter.Frame(up_window)#左上角设置参数用的容器
#image_frame.geometry('700x500')  # 这里的乘是小x
statustext_frame=tkinter.Frame(down_window,bg='blue')#右下角设置参数用的容器

##################下面是把设置区定义每行
setup_frame_line1=tkinter.Frame(setup_frame,bg='pink')#setup的第1行左上角设置参数用的容器
setup_frame_line2=tkinter.Frame(setup_frame,bg='pink')#setup的第2行左上角设置参数用的容器
setup_frame_line3=tkinter.Frame(setup_frame,bg='pink')#setup的第3行左上角设置参数用的容器
setup_frame_line4=tkinter.Frame(setup_frame,bg='pink')#setup的第4行左上角设置参数用的容器
setup_frame_line5=tkinter.Frame(setup_frame,bg='pink')#setup的第5行左上角设置参数用的容器
setup_frame_line6=tkinter.Frame(setup_frame,bg='pink')#setup的第6行左上角设置参数用的容器
setup_frame_line7=tkinter.Frame(setup_frame,bg='pink')#setup的第7行左上角设置参数用的容器
setup_frame_line8=tkinter.Frame(setup_frame,bg='pink')#setup的第8行左上角设置参数用的容器
setup_frame_line9=tkinter.Frame(setup_frame,bg='pink')#setup的第9行左上角设置参数用的容器
setup_frame_line10=tkinter.Frame(setup_frame,bg='pink')#setup的第10行左上角设置参数用的容器



#######################下面是把右边图像显示区定义
##右边image_frame的控件
panel = tkinter.Label(image_frame)  # initialize image panel


#############################左边setup_frame的控件
#############这是定义连接控件的变量
IP_addr_var=tkinter.StringVar()#本机IP值连接上LABEL
IP_addr_var.set(local_IP_addr)#将获取的本机IP显示出来

IP_port_var=tkinter.StringVar()#本机port值连接上LABEL
IP_port_var.set(format(PORT))#将获取的本机port显示出来

findline_pixcels_value_var=tkinter.StringVar()#本机port值连接上LABEL
findline_pixcels_value_var.set(format(findline_pixcels_setvalue))#将获取的本机port显示出来

PLC_addr_var=tkinter.StringVar()#本机IP值连接上LABEL
PLC_addr_var.set(PLC_addr)#将获取的本机IP显示出来

set_height_var=tkinter.StringVar()#设置分辨率高
set_height_var.set(format(set_height))

set_width_var=tkinter.StringVar()#设置分辨率宽
set_width_var.set(format(set_width))

bilateralfilter_var1=tkinter.StringVar()#双边滤波第一个参数连接上ENTRY
bilateralfilter_var1.set(format(bilateralfilter_var_1))

bilateralfilter_var2=tkinter.StringVar()#双边滤波第一个参数连接上ENTRY
bilateralfilter_var2.set(format(bilateralfilter_var_2))

bilateralfilter_var3=tkinter.StringVar()#双边滤波第一个参数连接上ENTRY
bilateralfilter_var3.set(format(bilateralfilter_var_3))

canny_var1=tkinter.StringVar()#canny边缘检测第一个参数连接上ENTRY
canny_var1.set(format(canny_var_1))

canny_var2=tkinter.StringVar()#canny边缘检测第一个参数连接上ENTRY
canny_var2.set(format(canny_var_2))

findline_pixcels_value_var=tkinter.StringVar()#检测边缘的像素限值连接上ENTRY
findline_pixcels_value_var.set(format(findline_pixcels_setvalue))#将检测边缘的像素限值显示出来

recordvideo_seconds_set_entry_var=tkinter.StringVar()#录像时长（秒）：连接上ENTRY
recordvideo_seconds_set_entry_var.set(format(recordvideo_seconds))#将录像时长（秒）：显示出来format(recordvideo_seconds)

output_pixcel_var=tkinter.StringVar()#输出值显示栏连接LABEL
output_pixcel_var.set(format(col_drawline))


##############################下面是定义设置区的控件
name=tkinter.Label(setup_frame_line1,text='恒大高新－－HCMT焊道自动纠偏系统V2.4',bg='pink',font=('黑体',12))

IP_label=tkinter.Label(setup_frame_line2,text='本地的IP地址：',bg='green')
IP_addr=tkinter.Label(setup_frame_line2,textvariable=IP_addr_var,text='本地的IP地址',bg='black',fg='white')

IP_port_label=tkinter.Label(setup_frame_line3,text='本地的端口号：', bg='green')
IP_port=tkinter.Label(setup_frame_line3,textvariable=IP_port_var,text='端口号', bg='black',fg='white')

set_resolution_label=tkinter.Label(setup_frame_line10,text='分辨率设置：', bg='green')
height_label=tkinter.Label(setup_frame_line10,text='高＝', bg='green')
set_height_entry=tkinter.Entry(setup_frame_line10,textvariable=set_height_var,width=4, bg='white')
width_label=tkinter.Label(setup_frame_line10,text='宽＝', bg='green')
set_width_entry=tkinter.Entry(setup_frame_line10,textvariable=set_width_var,width=4, bg='white')

bilateralfilter_label=tkinter.Label(setup_frame_line4,text='bilateralfilter：', bg='green')
bilateralfilter_entry1=tkinter.Entry(setup_frame_line4,textvariable=bilateralfilter_var1,width=4, bg='white')
bilateralfilter_entry2=tkinter.Entry(setup_frame_line4,textvariable=bilateralfilter_var2,width=4, bg='white')
bilateralfilter_entry3=tkinter.Entry(setup_frame_line4,textvariable=bilateralfilter_var3,width=4, bg='white')

canny_label=tkinter.Label(setup_frame_line5,text='canny：', bg='green')
canny_entry1=tkinter.Entry(setup_frame_line5,textvariable=canny_var1,width=4, bg='white')
canny_entry2=tkinter.Entry(setup_frame_line5,textvariable=canny_var2,width=4, bg='white')

findline_pixcels=tkinter.Label(setup_frame_line6,text='检测边缘的像素限值', bg='green')
findline_pixcels_value=tkinter.Entry(setup_frame_line6,textvariable=findline_pixcels_value_var,width=4, bg='white')

output_pixcels_label=tkinter.Label(setup_frame_line6,text='输出值', bg='green')
output_pixcels=tkinter.Label(setup_frame_line6,textvariable=output_pixcel_var, bg='black',fg='white')

recordvideo_seconds_set_lable=tkinter.Label(setup_frame_line9,text='录像时长（秒）：', bg='green')
recordvideo_seconds_set_entry=tkinter.Entry(setup_frame_line9,textvariable=recordvideo_seconds_set_entry_var,width=4, bg='white')


saveimage_btn = tkinter.Button(setup_frame_line7, text="截图",bg='yellow', command=take_snapshot)
recordvideo_btn=tkinter.Button(setup_frame_line7, text="录像",bg='blue',fg='white', command=record_video)

PLC_IP_label=tkinter.Label(setup_frame_line8,text='连接上的PLC的IP地址：',bg='green')
PLC_IP_addr=tkinter.Label(setup_frame_line8,textvariable=PLC_addr_var,text='PLC的IP地址',bg='black',fg='white')
#################################

###右下方的状态信息栏
status_scrolledtext=scrolledtext.ScrolledText(statustext_frame,bg='white',fg='black',width=137,height=10,padx=5,pady=5)
status_scrolledtext.insert(tkinter.END,'Start at: '+format(ctime())+'\n')

#输入框的值
#清理检测边缘像素限值输入框
#findline_pixcels_value.delete(0,END)
#recordvideo_seconds_set_entry.delete(0,END)
#print('1=',recordvideo_seconds_set_entry.get())
#print('2=',recordvideo_seconds)
##将修改后的值显示出来，按回车显示
#findline_pixcels_value.insert(4, format(findline_pixcels_setvalue))
#window.update()
#######################这是输入框的响应事件的连接
findline_pixcels_value.bind("<Return>",set_findline_pixcels_setvalue)
recordvideo_seconds_set_entry.bind("<Return>",set_recordvideo_seconds)
set_width_entry.bind("<Return>",set_resolution_value)
bilateralfilter_entry1.bind("<Return>",set_bilateralfilter_var)
bilateralfilter_entry2.bind("<Return>",set_bilateralfilter_var)
bilateralfilter_entry3.bind("<Return>",set_bilateralfilter_var)
canny_entry1.bind("<Return>",set_canny_var)
canny_entry2.bind("<Return>",set_canny_var)



##########################################################
#下面是布局
root_frame.pack(fill='both')

up_window.pack(fill='x')
down_window.pack(fill='x')

statustext_frame.pack(fill='y',padx=5,pady=5,side='right')#放在东南角
image_frame.pack(fill='y',padx=5,pady=5,side='right')#放在窗口的东北角NE,,padx=10,pady=10,side='right'
setup_frame.pack(fill='y',padx=5,pady=5,side='right')#放在窗口的西北角NW,,side='left'



setup_frame_line1.pack(fill='x')
setup_frame_line2.pack(fill='x')
setup_frame_line3.pack(fill='x')
setup_frame_line10.pack(fill='x')
setup_frame_line4.pack(fill='x')
setup_frame_line5.pack(fill='x')
setup_frame_line6.pack(fill='x')
setup_frame_line9.pack(fill='x')
setup_frame_line7.pack(fill='x')
setup_frame_line8.pack(fill='x')



#右边image_frame的布局
panel.pack(anchor='ne')#放在窗口的东北角NE,,ipadx=10,ipady=10

status_scrolledtext.pack(anchor='ne')#放在窗口的东北角NE

#左边setup_frame的布局
name.pack(ipadx=10,ipady=10,padx=10,pady=10,anchor='center')
IP_label.pack(padx=10,pady=10,side='left')#,side='top')row=0, column=0,
IP_addr.pack(padx=0,pady=10,side='left')#,side='right')row=1, column=1,

IP_port_label.pack(padx=10,pady=10,side='left')#,side='top')#side='left')
IP_port.pack(padx=0,pady=10,side='left')#,side='right')

set_resolution_label.pack(padx=10,pady=10,side='left')#,side='top')
height_label.pack(padx=0,pady=10,side='left')#,side='top')
set_height_entry.pack(padx=0,pady=10,side='left')#,side='top')
width_label.pack(padx=10,pady=10,side='left')#,side='top')
set_width_entry.pack(padx=0,pady=10,side='left')#,side='top')

bilateralfilter_label.pack(padx=10,pady=10,side='left')#,side='top')
bilateralfilter_entry1.pack(padx=0,pady=10,side='left')#,side='right')
bilateralfilter_entry2.pack(padx=10,pady=10,side='left')#,side='right')
bilateralfilter_entry3.pack(padx=0,pady=10,side='left')#,side='right')

canny_label.pack(padx=10,pady=10,side='left')#,side='top')
canny_entry1.pack(padx=0,pady=10,side='left')#,side='right')
canny_entry2.pack(padx=10,pady=10,side='left')#,side='right')

findline_pixcels.pack(padx=10,pady=10,side='left')
findline_pixcels_value.pack(padx=0,pady=10,side='left')

output_pixcels.pack(padx=10,pady=10,side='right')
output_pixcels_label.pack(padx=0,pady=10,side='right')

recordvideo_seconds_set_lable.pack(padx=10,pady=10,side='left')
recordvideo_seconds_set_entry.pack(padx=0,pady=10,side='left')

PLC_IP_label.pack(padx=10,pady=10,side='left')
PLC_IP_addr.pack(padx=0,pady=10,side='left')

saveimage_btn.pack(padx=10,pady=10,ipadx=10,ipady=10,side='right')
recordvideo_btn.pack(padx=10,pady=10,ipadx=10,ipady=10,side='left')


##################################开始显示窗口，开始执行

window.state('zoomed')#在WINDOWS系统中可以用，使窗口打开为最大化
#w, h = window.maxsize()#获取窗口最大化时的宽和高
#window.geometry("{}x{}".format(w, h)) #看好了，中间的是小写字母x
#w = window.winfo_screenwidth()
#h = window.winfo_screenheight()
#window.geometry("%dx%d" %(w, h))

#recordvideo_seconds_set_entry_var.set('OK')#将录像时长（秒）：显示出来format(recordvideo_seconds)

read_setup_file()#读取配置文件
waiting_for_connecting()#等待PLC等客户端的连接
video_loop()#循环读取摄像头的每一帧
#accept_client()

status_scrolledtext_gettext=status_scrolledtext.get('0.0',tkinter.END)
window.mainloop()#开始窗口消息循环

#########################################以下是执行了关闭后，执行下面
# 当一切都完成后，关闭摄像头并释放所占资源
cap.release()




c.close()
s.close()

###########################将参数写入配置文件中
write_setup_file=''
if (not parameter_names)or(not parameter_values):
    print('没有读取到配置文件，所以不保存参数。')
else:
    
    for name in range(len(parameter_names)):
        
        write_setup_file=write_setup_file+(str(parameter_names[name])+str(parameter_values[name])+'\n')
        
    print(write_setup_file)
    setup_file=open('HCMT_Weld_Bead_Rectification_System.ini',mode='w')

    setup_file.write(write_setup_file)
    setup_file.close()

log_file=open('HCMT_Weld_Bead_Rectification_System.log',mode='a')
log_file.write(format(status_scrolledtext_gettext))#'0.0',tkinter.END
log_file.close()
print('the end')
cv2.destroyAllWindows()
