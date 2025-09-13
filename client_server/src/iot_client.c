/* 서울기술 교육센터 IoT */
/* Enhanced Client - Text, File Transfer, Voice Recognition and Camera Support with Voice Response */
/* author : KSH */
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <string.h>
#include <arpa/inet.h>
#include <sys/types.h>
#include <sys/socket.h>
#include <pthread.h>
#include <signal.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <sys/wait.h>

#define BUF_SIZE 1024
#define NAME_SIZE 20
#define ARR_CNT 5
#define FILE_BUF_SIZE 8192
#define MAX_FILENAME 256

// 메시지 타입 정의
#define MSG_TYPE_TEXT 1
#define MSG_TYPE_FILE 2
#define MSG_TYPE_FILE_INFO 3

// 프로토콜 구조체
typedef struct {
    int msg_type;
    int data_size;
    char filename[MAX_FILENAME];
    char sender[NAME_SIZE];
} msg_header_t;

// 함수 선언
void * send_msg(void * arg);
void * recv_msg(void * arg);
void error_handling(char * msg);
int send_file(int sock, char *filepath);
int recv_file(int sock, char *filename, int filesize);
void show_help(void);
int start_voice_recognition(int sock);
int capture_and_send_images(int sock);
int text_to_speech_response(char *text);  // 새로 추가된 함수

char name[NAME_SIZE]="[Default]";
char msg[BUF_SIZE];

int main(int argc, char *argv[])
{
    int sock;
    struct sockaddr_in serv_addr;
    pthread_t snd_thread, rcv_thread;
    void * thread_return;

    if(argc != 4) {
        printf("Usage : %s <IP> <port> <name>\n",argv[0]);
        exit(1);
    }

    sprintf(name, "%s",argv[3]);

    sock = socket(PF_INET, SOCK_STREAM, 0);
    if(sock == -1)
        error_handling("socket() error");

    memset(&serv_addr, 0, sizeof(serv_addr));
    serv_addr.sin_family=AF_INET;
    serv_addr.sin_addr.s_addr = inet_addr(argv[1]);
    serv_addr.sin_port = htons(atoi(argv[2]));

    if(connect(sock, (struct sockaddr *)&serv_addr, sizeof(serv_addr)) == -1)
        error_handling("connect() error");

    sprintf(msg,"[%s:PASSWD]",name);
    write(sock, msg, strlen(msg));
    
    pthread_create(&rcv_thread, NULL, recv_msg, (void *)&sock);
    pthread_create(&snd_thread, NULL, send_msg, (void *)&sock);

    pthread_join(snd_thread, &thread_return);
    //	pthread_join(rcv_thread, &thread_return);

    close(sock);
    return 0;
}

void * send_msg(void * arg)
{
    int *sock = (int *)arg;
    int str_len;
    int ret;
    fd_set initset, newset;
    struct timeval tv;
    char name_msg[NAME_SIZE + BUF_SIZE+2];
    char input[BUF_SIZE];

    FD_ZERO(&initset);
    FD_SET(STDIN_FILENO, &initset);

    printf("\n=== Enhanced Chat Client with Voice Recognition and Camera ===\n");
    printf("Commands:\n");
    printf("  1            - Start voice recognition\n");
    printf("  2            - Capture RGB image and send to server\n");  // Depth 이미지 제거 명시
    printf("  3            - Toggle voice response mode (ON/OFF)\n");
    printf("  [ID]message  - Send text message to specific ID (Default: ALLMSG)\n");
    printf("  /file <path> - Send file\n");
    printf("  /help        - Show this help\n");
    printf("  quit         - Exit\n");
    printf("===============================================================\n\n");

    while(1) {
        memset(input,0,sizeof(input));
        name_msg[0] = '\0';
        tv.tv_sec = 1;
        tv.tv_usec = 0;
        newset = initset;
        ret = select(STDIN_FILENO + 1, &newset, NULL, NULL, &tv);
        
        if(FD_ISSET(STDIN_FILENO, &newset))
        {
            fgets(input, BUF_SIZE, stdin);
            
            // quit 명령어 처리
            if(!strncmp(input,"quit\n",5)) {
                *sock = -1;
                return NULL;
            }
            // help 명령어 처리
            else if(!strncmp(input,"/help\n",6)) {
                show_help();
                continue;
            }
            // 음성인식 명령어 처리 (1 입력)
            else if(!strncmp(input,"1\n",2)) {
                printf("음성인식을 시작합니다...\n");
                start_voice_recognition(*sock);
                continue;
            }
            // 카메라 캡처 명령어 처리 (2 입력)
            else if(!strncmp(input,"2\n",2)) {
                printf("RGB 이미지를 캡처하고 서버로 전송합니다...\n");
                capture_and_send_images(*sock);
                continue;
            }
            // 음성 응답 토글 명령어 처리 (3 입력) - 새로 추가
            else if(!strncmp(input,"3\n",2)) {
                printf("음성 응답 모드 토글 기능은 현재 개발 중입니다.\n");
                continue;
            }
            // 파일 전송 명령어 처리
            else if(!strncmp(input,"/file ",6)) {
                char *filepath = input + 6; // "/file " 제거
                filepath[strlen(filepath)-1] = '\0'; // 개행문자 제거
                
                if(send_file(*sock, filepath) < 0) {
                    printf("File send failed: %s\n", filepath);
                } else {
                    printf("File sent successfully: %s\n", filepath);
                }
                continue;
            }
            // 일반 텍스트 메시지 처리
            else {
                // 변경
                if (input[0] != '[') {
                    snprintf(name_msg, sizeof(name_msg), "[ALL] %s", input);
                } else {
                    strncpy(name_msg, input, sizeof(name_msg)-1);
                    name_msg[sizeof(name_msg)-1] = '\0';
                }
                
                if(write(*sock, name_msg, strlen(name_msg))<=0)
                {
                    *sock = -1;
                    return NULL;
                }
            }
        }
        if(ret == 0) 
        {
            if(*sock == -1) 
                return NULL;
        }
    }
}

void * recv_msg(void * arg)
{
    int * sock = (int *)arg;	
    int i;
    char *pToken;
    char *pArray[ARR_CNT]={0};

    char name_msg[NAME_SIZE + BUF_SIZE +1];
    int str_len;
    
    while(1) {
        memset(name_msg,0x0,sizeof(name_msg));
        str_len = read(*sock, name_msg, NAME_SIZE + BUF_SIZE );
        if(str_len <= 0) 
        {
            *sock = -1;
            return NULL;
        }
        name_msg[str_len] = 0;
        
        // 파일 전송 알림인지 확인
        if(strstr(name_msg, "[FILE:") != NULL) {
            printf("\n=== File Transfer Notification ===\n");
            printf("%s\n", name_msg);
            printf("=====================================\n");
        } 
        // 서버에서 온 일반 텍스트 메시지인지 확인 (음성 응답 대상)
        else if(strstr(name_msg, "Connected!") != NULL) {
            // 연결 메시지는 화면에만 출력하고 음성 변환은 하지 않음
            fputs(name_msg, stdout);
        } 
        else if(strstr(name_msg, "[") != NULL && strstr(name_msg, "]") != NULL) {
            // 메시지를 화면에 출력
            fputs(name_msg, stdout);
            
            // 음성 응답 기능 호출
            // 메시지에서 실제 텍스트 부분만 추출하여 음성으로 변환
            char *text_start = strchr(name_msg, ']');
            if(text_start != NULL) {
                text_start++; // ']' 다음 문자부터
                // 앞뒤 공백 제거
                while(*text_start == ' ' || *text_start == '\t') text_start++;
                
                char *text_end = text_start + strlen(text_start) - 1;
                while(text_end > text_start && (*text_end == ' ' || *text_end == '\t' || *text_end == '\n' || *text_end == '\r')) {
                    *text_end = '\0';
                    text_end--;
                }
                
                // 텍스트가 충분히 길고 의미있는 경우에만 음성 변환
                if(strlen(text_start) > 3) {
                    // Python TTS 스크립트를 직접 호출
                    text_to_speech_response(text_start);
                }
            }
        } 
        else {
            // 일반 메시지 출력
            fputs(name_msg, stdout);
        }
    }
}

// Python TTS 스크립트를 호출하는 함수
int text_to_speech_response(char *text)
{
    pid_t pid = fork();
    if(pid == 0) {
        // 자식 프로세스: Python TTS 스크립트를 직접 실행
        // python3 text_to_speech.py "텍스트내용" 형태로 실행
        execlp("python3", "python3", "text_to_speech.py", text, NULL);
        // execlp가 실패하면 여기로 옴
        exit(1);
    } else if(pid > 0) {
        // 부모 프로세스: 자식 프로세스를 백그라운드에서 실행
        // 메인 채팅 기능을 방해하지 않도록 논블로킹으로 처리
        printf("음성을 출력합니다...\n");
        return 0;
    } else {
        printf("음성 출력 프로세스 생성 실패\n");
        return -1;
    }
}

int capture_and_send_images(int sock)
{
    pid_t pid = fork();
    if(pid == 0) {
        // 자식 프로세스: Python 카메라 스크립트 실행
        execlp("python3", "python3", "camera_capture.py", NULL);
        exit(1);
    } else if(pid > 0) {
        // 부모 프로세스: 자식 프로세스 완료 대기
        int status;
        waitpid(pid, &status, 0);
        
        if(WIFEXITED(status) && WEXITSTATUS(status) == 0) {
            printf("이미지 캡처가 완료되었습니다.\n");
            
            // RGB 이미지만 전송 (Depth 이미지 전송 제거)
            char rgb_filename[] = "captured_rgb.jpg";
            if(access(rgb_filename, F_OK) == 0) {
                printf("RGB 이미지를 서버로 전송합니다...\n");
                if(send_file(sock, rgb_filename) < 0) {
                    printf("RGB 이미지 전송 실패\n");
                } else {
                    printf("RGB 이미지 전송 완료\n");
                }
            }
            
            // 임시 파일 삭제 (RGB 이미지만)
            unlink(rgb_filename);
            
        } else {
            printf("이미지 캡처 실패\n");
            return -1;
        }
    } else {
        printf("프로세스 생성 실패\n");
        return -1;
    }
    
    return 0;
}

int start_voice_recognition(int sock)
{
    char voice_text[BUF_SIZE];
    memset(voice_text, 0, sizeof(voice_text));
    
    // 파이프 생성
    int pipe_fd[2];
    if(pipe(pipe_fd) == -1) {
        printf("파이프 생성 실패\n");
        return -1;
    }
    
    pid_t pid = fork();
    if(pid == 0) {
        // 자식 프로세스: Python 음성인식 실행
        close(pipe_fd[0]); // 읽기 끝 닫기
        dup2(pipe_fd[1], STDOUT_FILENO); // 표준출력을 파이프로 리다이렉트
        close(pipe_fd[1]);
        
        // Python 음성인식 스크립트 실행
        execlp("python3", "python3", "voice_recognition.py", NULL);
        exit(1);
    } else if(pid > 0) {
        // 부모 프로세스: 파이프에서 결과 읽기
        close(pipe_fd[1]); // 쓰기 끝 닫기
        
        printf("음성을 입력하세요...\n");
        int bytes_read = read(pipe_fd[0], voice_text, BUF_SIZE-1);
        close(pipe_fd[0]);
        
        if(bytes_read > 0) {
            voice_text[bytes_read] = '\0';
            // 개행문자 제거
            if(voice_text[strlen(voice_text)-1] == '\n') {
                voice_text[strlen(voice_text)-1] = '\0';
            }
            
            printf("인식된 텍스트: %s\n", voice_text);
            
            // 서버로 음성인식 결과 전송
            char voice_msg[BUF_SIZE];
            int msg_len = snprintf(voice_msg, BUF_SIZE, "TEXT:%s\n", voice_text);
            
            // 버퍼 오버플로우 방지
            if(msg_len >= BUF_SIZE) {
                voice_msg[BUF_SIZE-1] = '\0';
                msg_len = BUF_SIZE-1;
            }
            
            if(write(sock, voice_msg, strlen(voice_msg)) <= 0) {
                printf("음성인식 결과 전송 실패\n");
                return -1;
            } else {
                printf("음성인식 결과를 서버로 전송했습니다.\n");
            }
        } else {
            printf("음성인식 실패\n");
        }
        
        wait(NULL); // 자식 프로세스 종료 대기
    } else {
        printf("프로세스 생성 실패\n");
        close(pipe_fd[0]);
        close(pipe_fd[1]);
        return -1;
    }
    
    return 0;
}

int send_file(int sock, char *filepath){
    FILE *file;
    struct stat file_stat;
    char buffer[BUF_SIZE];
    size_t bytes_read;
    int total_sent = 0;
    
    // 파일 존재 확인
    if(stat(filepath, &file_stat) != 0) {
        printf("Error: File not found - %s\n", filepath);
        return -1;
    }
    
    // 파일 열기
    file = fopen(filepath, "rb");
    if(file == NULL) {
        printf("Error: Cannot open file - %s\n", filepath);
        return -1;
    }
    
    // 파일명 추출 (경로에서 파일명만)
    char *filename = strrchr(filepath, '/');
    if(filename == NULL) {
        filename = strrchr(filepath, '\\');
    }
    if(filename == NULL) {
        filename = filepath;
    } else {
        filename++; // '/' 또는 '\' 다음부터
    }
    
    // ✅ 서버가 인식하는 헤더 형식으로 변경: IMAGE:<파일명>:<파일크기>\n
    char header_str[512];
    snprintf(header_str, sizeof(header_str), "IMAGE:%s:%ld\n", filename, file_stat.st_size);

    // ✅ 수정된 헤더를 서버에 전송
    if (write(sock, header_str, strlen(header_str)) <= 0) {
        printf("Error: Failed to send image header\n");
        fclose(file);
        return -1;
    }
    
    // 파일 데이터 전송
    while((bytes_read = fread(buffer, 1, sizeof(buffer), file)) > 0) {
        if(write(sock, buffer, bytes_read) != bytes_read) {
            printf("Error: Failed to send file data\n");
            fclose(file);
            return -1;
        }
        total_sent += bytes_read;
        
        // 진행률 표시
        printf("\rSending: %d/%ld bytes (%.1f%%)", 
               total_sent, file_stat.st_size, 
               (float)total_sent/file_stat.st_size*100);
        fflush(stdout);
    }
    
    printf("\n");
    fclose(file);
    return total_sent;
}

int recv_file(int sock, char *filename, int filesize)
{
    FILE *file;
    char buffer[FILE_BUF_SIZE];
    int bytes_received = 0;
    int bytes_to_read;
    
    // 파일 생성
    file = fopen(filename, "wb");
    if(file == NULL) {
        printf("Error: Cannot create file - %s\n", filename);
        return -1;
    }
    
    // 파일 데이터 수신
    while(bytes_received < filesize) {
        bytes_to_read = (filesize - bytes_received > FILE_BUF_SIZE) ? 
                        FILE_BUF_SIZE : (filesize - bytes_received);
        
        int n = read(sock, buffer, bytes_to_read);
        if(n <= 0) {
            printf("Error: Failed to receive file data\n");
            fclose(file);
            return -1;
        }
        
        if(fwrite(buffer, 1, n, file) != n) {
            printf("Error: Failed to write file data\n");
            fclose(file);
            return -1;
        }
        
        bytes_received += n;
        
        // 진행률 표시
        printf("\rReceiving: %d/%d bytes (%.1f%%)", 
               bytes_received, filesize, 
               (float)bytes_received/filesize*100);
        fflush(stdout);
    }
    
    printf("\n");
    fclose(file);
    return bytes_received;
}

void show_help(void)
{
    printf("\n=== Help ===\n");
    printf("Voice Recognition:\n");
    printf("  1            - Start voice recognition and send result to server\n");
    printf("\nCamera Capture:\n");
    printf("  2            - Capture RGB image and send to server\n");
    printf("\nVoice Response:\n");
    printf("  3            - Toggle voice response mode (ON/OFF)\n");
    printf("\nText Messages:\n");
    printf("  [ID]message  - Send message to specific user ID\n");
    printf("  message      - Send message to all users (ALLMSG)\n");
    printf("\nFile Transfer:\n");
    printf("  /file <path> - Send file (images, documents, etc.)\n");
    printf("  Example: /file /home/user/image.jpg\n");
    printf("\nOther Commands:\n");
    printf("  /help        - Show this help\n");
    printf("  quit         - Exit the program\n");
    printf("\nNote: Server responses will be automatically converted to speech\n");
    printf("==============\n\n");
}

void error_handling(char * msg)
{
    fputs(msg, stderr);
    fputc('\n', stderr);
    exit(1);
}
