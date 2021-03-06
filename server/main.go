package main

import (
	"context"
	"io"
	"io/ioutil"
	"net"
	"os"
	"path/filepath"
	"runtime"
	"time"

	"github.com/joho/godotenv"
	"github.com/krnblni/UnitedShieldSpace/server/auth"
	"github.com/krnblni/UnitedShieldSpace/server/crypt"
	"github.com/krnblni/UnitedShieldSpace/server/db"
	"github.com/krnblni/UnitedShieldSpace/server/firebase"
	"github.com/krnblni/UnitedShieldSpace/server/logger"
	"github.com/krnblni/UnitedShieldSpace/server/models"
	"github.com/krnblni/UnitedShieldSpace/server/utils"
	"go.mongodb.org/mongo-driver/bson/primitive"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"

	unitedShieldSpace "github.com/krnblni/UnitedShieldSpace/server/genproto"
)

// get logger instance
var ussLogger = logger.GetInstance()

func init() {
	// get current path
	_, fileName, _, _ := runtime.Caller(0)
	currentPath := filepath.Dir(fileName)

	// Load .env file
	if err := godotenv.Load(currentPath + "/.env"); err != nil {
		ussLogger.Println("Error loading .env file: ", err)
	}
}

type ussServer struct{}

func (u *ussServer) RegisterNewUser(ctx context.Context, newUserDetails *unitedShieldSpace.NewUserDetails) (*unitedShieldSpace.UserCreationStatus, error) {
	err := utils.ValidateNewUserDetails(newUserDetails)
	if err != nil {
		return &unitedShieldSpace.UserCreationStatus{UserCreated: false}, status.Error(codes.InvalidArgument, "Invalid user details")
	}

	err = db.CreateNewUser(newUserDetails)
	if err != nil {
		return &unitedShieldSpace.UserCreationStatus{UserCreated: false}, err
	}

	return &unitedShieldSpace.UserCreationStatus{UserCreated: true}, nil
}

func (u *ussServer) LoginUser(ctx context.Context, userCredentials *unitedShieldSpace.UserCredentials) (*unitedShieldSpace.LoginResponse, error) {
	err := utils.ValidateUserCredentials(userCredentials)
	if err != nil {
		return &unitedShieldSpace.LoginResponse{LoginStatus: false}, status.Error(codes.InvalidArgument, "Invalid user credentials")
	}

	return auth.Login(userCredentials)
}

func (u *ussServer) UploadFile(stream unitedShieldSpace.UnitedShieldSpace_UploadFileServer) error {

	fileSegmentWithToken, err := stream.Recv()
	if err != nil {
		return status.Error(codes.Internal, "grpc stream error")
	}

	// this file segment is meant to contain no file data but tokens only
	// verify tokens
	authStatus := auth.VerifyAccessToken(fileSegmentWithToken.GetAccessToken())
	if authStatus == codes.Unauthenticated {
		return status.Error(codes.Unauthenticated, "invalid access token")
	}

	clientFileName := fileSegmentWithToken.GetFileName()
	userEmail := fileSegmentWithToken.GetEmail()
	userID := fileSegmentWithToken.GetUid()

	_, filename, _, _ := runtime.Caller(0)
	// doing this so that from where ever the user runs this file,
	// the temp file will be stored in this directory only
	currentPath := filepath.Dir(filename)
	tempFile, err := ioutil.TempFile(currentPath+"/tempfiles", clientFileName)
	defer os.Remove(tempFile.Name())
	defer os.Remove(tempFile.Name() + ".enc")

	// if we are here means token is valid
	// start reading file from the stream
	for {
		fileSegment, err := stream.Recv()
		if err == io.EOF {
			// means whole file is recieved
			// we can now encrypt the file
			encyptionStatus := crypt.EncryptClientFile(tempFile.Name())
			if !encyptionStatus {
				return status.Error(codes.Internal, "internal server error")
			}

			// now here we can start to upload file to firebase storage
			firebaseUploadStatus := firebase.UplaodFileToStorage(tempFile.Name(), clientFileName, userEmail)

			if !firebaseUploadStatus {
				return status.Error(codes.Internal, "internal server error")
			}

			// here means firebase file uploaded
			// create node
			node := &models.FileNode{
				ID:      userEmail + userID + clientFileName,
				Owner:   userEmail,
				Name:    clientFileName,
				ACL:     make([]primitive.D, 0),
				Created: time.Now().Unix(),
			}
			nodeCreationStatus := db.CreateNewFileNode(node)

			if !nodeCreationStatus {
				ussLogger.Println("unable to create file node in files collection")
				return status.Error(codes.Internal, "internal server error")
			}

			// here means node is also created on mongo db files collection
			return stream.SendAndClose(&unitedShieldSpace.UploadStatus{
				UploadStatus: true,
			})
		}
		if err != nil {
			return status.Error(codes.Internal, "grpc stream error")
		}

		// now we can read the file
		segmentData := fileSegment.GetFileSegmentData()
		if _, err := tempFile.Write(segmentData); err != nil {
			ussLogger.Println("Error writing to file...", err)
		}
	}
}

func (u *ussServer) GetNewTokens(ctx context.Context, refreshTokenDetails *unitedShieldSpace.RefreshTokenDetails) (*unitedShieldSpace.NewTokens, error) {
	ussLogger.Println("Renewing Tokens")
	authstatus := auth.VerifyRefreshToken(refreshTokenDetails.GetRefreshToken(), refreshTokenDetails.GetUid())
	if authstatus == codes.Unauthenticated {
		return &unitedShieldSpace.NewTokens{
			AccessToken:  "",
			RefreshToken: "",
		}, status.Error(codes.Unauthenticated, "internal error sign in again")
	}

	// here means refresh token is valid
	// generate new tokens
	return auth.RenewTokens(refreshTokenDetails.GetUid())
}

func (u *ussServer) ListUserFiles(userDetails *unitedShieldSpace.UserDetails, stream unitedShieldSpace.UnitedShieldSpace_ListUserFilesServer) error {
	ussLogger.Println("List user files was called...")
	// verify access token here first
	authStatus := auth.VerifyAccessToken(userDetails.GetAccessToken())
	if authStatus == codes.Unauthenticated {
		return status.Error(codes.Unauthenticated, "invalid access token")
	}

	userFilesList, err := db.FetchUserFiles(userDetails.GetEmail())
	if err != nil {
		return status.Error(codes.Internal, "internal server error")
	}

	if len(userFilesList) == 0 {
		return status.Error(codes.NotFound, "no files found")
	}

	for _, userFile := range userFilesList {
		fileDetail := &unitedShieldSpace.FileDetails{
			Name:      userFile.Name,
			CreatedOn: userFile.Created,
		}
		ussLogger.Println(fileDetail)
		if err := stream.Send(fileDetail); err != nil {
			ussLogger.Println("error sending the file details", err)
			return status.Error(codes.Internal, "internal server error")
		}
	}

	return nil
}

func (u *ussServer) ListSharedWithMeFiles(userDetails *unitedShieldSpace.UserDetails, stream unitedShieldSpace.UnitedShieldSpace_ListSharedWithMeFilesServer) error {
	ussLogger.Println("List user files was called...")
	// verify access token here first
	authStatus := auth.VerifyAccessToken(userDetails.GetAccessToken())
	if authStatus == codes.Unauthenticated {
		return status.Error(codes.Unauthenticated, "invalid access token")
	}

	sharedWithMeFilesList, err := db.FetchSharedWithMeFiles(userDetails.GetEmail())
	if err != nil {
		return status.Error(codes.Internal, "internal server error")
	}

	if len(sharedWithMeFilesList) == 0 {
		return status.Error(codes.NotFound, "no files found")
	}

	for _, sharedWithMeFile := range sharedWithMeFilesList {
		extFileDetail := &unitedShieldSpace.ExtFileDetails{
			Name:      sharedWithMeFile.Name,
			Owner:     sharedWithMeFile.Owner,
			CreatedOn: sharedWithMeFile.Created,
		}
		ussLogger.Println(extFileDetail)
		if err := stream.Send(extFileDetail); err != nil {
			ussLogger.Println("error sending the file details", err)
			return status.Error(codes.Internal, "internal server error")
		}
	}

	return nil
}

func (u *ussServer) UpdateACL(ctx context.Context, aclDetails *unitedShieldSpace.ACLDetails) (*unitedShieldSpace.ACLUpdateResponse, error) {

	// this file segment is meant to contain no file data but tokens only
	// verify tokens
	authStatus := auth.VerifyAccessToken(aclDetails.GetAccessToken())
	if authStatus == codes.Unauthenticated {
		return &unitedShieldSpace.ACLUpdateResponse{
			ACLUpdateStatus: false,
		}, status.Error(codes.Unauthenticated, "invalid access token")
	}

	// means accesstoken is valid
	return db.UpdateFileACL(aclDetails)
}

func (u *ussServer) GetFileToken(ctx context.Context, fileTokenParams *unitedShieldSpace.FileTokenParams) (*unitedShieldSpace.FileTokenResponse, error) {

	// verify token
	authStatus := auth.VerifyAccessToken(fileTokenParams.GetAccessToken())
	if authStatus == codes.Unauthenticated {
		return &unitedShieldSpace.FileTokenResponse{
			FileToken: "",
		}, status.Error(codes.Unauthenticated, "invalid access token")
	}

	// means access token is valid
	fileSalt, err := db.GetFileSalt(fileTokenParams.GetOwner(), fileTokenParams.GetName(), fileTokenParams.GetRequestor())
	if err != nil {
		return &unitedShieldSpace.FileTokenResponse{
			FileToken: "",
		}, status.Error(codes.Internal, "internal server error")
	}

	ussLogger.Println("salt used in token creation - ", fileSalt)
	fileTokenString, err := auth.GetFileTokenWithParams(fileTokenParams.GetOwner(), fileTokenParams.GetRequestor(), fileSalt, fileTokenParams.GetName())
	if err != nil {
		return &unitedShieldSpace.FileTokenResponse{
			FileToken: "",
		}, status.Error(codes.Internal, "internal server error")
	}

	return &unitedShieldSpace.FileTokenResponse{
		FileToken: fileTokenString,
	}, nil
}

func (u *ussServer) DownloadFile(requestedFileDetails *unitedShieldSpace.RequestedFileDetails, stream unitedShieldSpace.UnitedShieldSpace_DownloadFileServer) error {
	// verify token
	authStatus := auth.VerifyAccessToken(requestedFileDetails.GetAccessToken())
	if authStatus == codes.Unauthenticated {
		return status.Error(codes.Unauthenticated, "invalid access token")
	}

	// get salt from database
	fileSalt, err := db.GetFileSaltAndIncrease(requestedFileDetails.GetOwner(), requestedFileDetails.GetName(), requestedFileDetails.GetRequestor())
	if err != nil {
		return status.Error(codes.Internal, "internal server error")
	}

	// verify file token
	fileTokenStatus := auth.VerifyFileToken(requestedFileDetails.GetFileToken(), fileSalt)
	ussLogger.Println(fileTokenStatus)
	if fileTokenStatus == codes.Unauthenticated {
		return status.Error(codes.Unauthenticated, "invalid file access token")
	}

	// file access token is valid
	// download file from firebase
	encFile, downloadStatus := firebase.DownlaodFileFromStorage(requestedFileDetails.GetName(), requestedFileDetails.GetOwner())
	if !downloadStatus {
		ussLogger.Println("Unable to download file")
	}

	ussLogger.Println(encFile)
	decryptStatus := crypt.DecryptClientFile(encFile)

	if !decryptStatus {
		return status.Error(codes.Internal, "internal server error")
	}

	// sending file on stream
	file, err := os.Open(encFile + ".txt")
	if err != nil {
		ussLogger.Println("unable to open decrypted file - ", err)
		return status.Error(codes.Internal, "internal server error")
	}
	defer file.Close()

	defer os.Remove(encFile)
	defer os.Remove(encFile + ".txt")

	bufferSize := 128
	buffer := make([]byte, bufferSize)

	for {
		numberOfBytesRead, err := file.Read(buffer)
		if err == io.EOF {
			return nil
		}

		if err != nil {
			ussLogger.Println("error reading file - ", err)
			return status.Error(codes.Internal, "internal server error")
		}

		stream.Send(&unitedShieldSpace.RequestedFileSegments{
			FileSegmentData: buffer[:numberOfBytesRead],
		})
	}
}

func main() {
	// get port number as string
	port := utils.GetEnvAsString("PORT", "7000")

	// create a listener to server port
	listener, err := net.Listen("tcp", ":"+port)
	if err != nil {
		ussLogger.Println("Unable to create a listener: ", err)
	}

	server := grpc.NewServer()

	unitedShieldSpace.RegisterUnitedShieldSpaceServer(server, &ussServer{})

	ussLogger.Println("Starting server on port: ", port)

	if err := server.Serve(listener); err != nil {
		ussLogger.Println("Unable to create server: ", err)
	}
}
